import time
import json
import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class PMCServicesScraper:
    def __init__(self, headless=False):
        """Initialize the scraper with Chrome driver"""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 15)
        self.services_data = []
        
    def scrape_services(self, url="https://services.pmc.gov.in/home"):
        """Main method to scrape all services"""
        print("🚀 Loading PMC services page...")
        self.driver.get(url)
        
        # Wait for page to load completely
        print("⏳ Waiting for services to load...")
        time.sleep(5)
        
        try:
            # Find all service items using the exact selector from the page
            service_elements = self.driver.find_elements(By.CSS_SELECTOR, ".service-item")
            print(f"✅ Found {len(service_elements)} services to process")
            
            if not service_elements:
                print("❌ No service items found! Check if page loaded correctly.")
                return self.services_data
                
            # Process each service
            for i, service_element in enumerate(service_elements):
                print(f"📋 Processing service {i+1}/{len(service_elements)}...")
                self.process_service(service_element, i)
                time.sleep(1.5)  # Be polite to the server
                
        except Exception as e:
            print(f"❌ Error during scraping: {str(e)}")
            
        return self.services_data
    
    def process_service(self, service_element, index):
        """Process individual service and extract description"""
        try:
            # Get service name and ID
            service_name = service_element.text.strip()
            service_id = service_element.get_attribute('id')
            
            print(f"   🎯 Clicking on: {service_name[:50]}...")
            
            # Scroll element into view and click
            self.driver.execute_script("arguments[0].scrollIntoView(true);", service_element)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", service_element)
            
            # Wait for modal to appear
            time.sleep(3)
            
            # Extract service details from the modal
            service_details = self.extract_service_details()
            
            # Store the data
            service_data = {
                'index': index + 1,
                'service_id': service_id,
                'name': service_name,
                'description': service_details.get('description', 'No description available'),
                'process': service_details.get('process', 'No process available'),
                'documents': service_details.get('documents', 'No documents information'),
                'fees': service_details.get('fees', 'No fees information')
            }
            
            self.services_data.append(service_data)
            print(f"   ✅ Extracted: {service_name[:50]}...")
            
            # Close the modal
            self.close_modal()
            time.sleep(1)
            
        except Exception as e:
            print(f"   ❌ Error processing service {index+1}: {str(e)}")
            self.close_modal()  # Try to close any open modal
    
    def extract_service_details(self):
        """Extract service details from the modal"""
        details = {
            'description': 'No description available',
            'process': 'No process available', 
            'documents': 'No documents information',
            'fees': 'No fees information'
        }
        
        try:
            # Wait for modal to be visible
            modal = self.wait.until(
                EC.visibility_of_element_located((By.ID, "modelWindow"))
            )
            
            # Wait a bit more for content to load
            time.sleep(2)
            
            # Get the modal text content
            modal_text = self.driver.find_element(By.ID, "modal-text")
            
            # Check if still loading
            if "bouncing-loader" in modal_text.get_attribute("innerHTML"):
                print("      ⏳ Content still loading, waiting...")
                time.sleep(3)
            
            # Extract different sections
            modal_html = modal_text.get_attribute("innerHTML")
            
            # Extract service description
            if "Service Description" in modal_html:
                try:
                    # Look for description paragraph
                    desc_elements = modal_text.find_elements(By.XPATH, ".//h3[contains(text(), 'Service Description')]/following-sibling::p")
                    if desc_elements:
                        details['description'] = desc_elements[0].text.strip()
                except:
                    pass
            
            # Extract process
            if "Process" in modal_html:
                try:
                    process_elements = modal_text.find_elements(By.XPATH, ".//h3[contains(text(), 'Process')]/following-sibling::p")
                    if process_elements:
                        details['process'] = process_elements[0].text.strip()
                except:
                    pass
            
            # Extract documents table
            if "Required Documents" in modal_html:
                try:
                    doc_tables = modal_text.find_elements(By.XPATH, ".//h3[contains(text(), 'Required Documents')]/following-sibling::table")
                    if doc_tables:
                        details['documents'] = doc_tables[0].text.strip()
                except:
                    pass
            
            # Extract fees table
            if "Fees Structure" in modal_html:
                try:
                    fee_tables = modal_text.find_elements(By.XPATH, ".//h3[contains(text(), 'Fees Structure')]/following-sibling::table")
                    if fee_tables:
                        details['fees'] = fee_tables[0].text.strip()
                except:
                    pass
            
            # If no specific sections found, get all text
            if all(v in ['No description available', 'No process available', 'No documents information', 'No fees information'] 
                   for v in details.values()):
                all_text = modal_text.text.strip()
                if all_text and len(all_text) > 50:
                    details['description'] = all_text[:500] + "..." if len(all_text) > 500 else all_text
                    
        except TimeoutException:
            print("      ⚠️ Modal took too long to load")
        except Exception as e:
            print(f"      ⚠️ Error extracting details: {str(e)}")
            
        return details
    
    def close_modal(self):
        """Close the modal window"""
        try:
            # Try multiple ways to close the modal
            close_methods = [
                # Try the close function
                lambda: self.driver.execute_script("closeModelWindow();"),
                # Try clicking the X button
                lambda: self.driver.find_element(By.CSS_SELECTOR, "span[onclick*='closeModelWindow']").click(),
                # Try ESC key
                lambda: self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE),
                # Try clicking outside modal
                lambda: self.driver.find_element(By.ID, "modelWindow").click()
            ]
            
            for method in close_methods:
                try:
                    method()
                    time.sleep(0.5)
                    # Check if modal is closed
                    modal = self.driver.find_element(By.ID, "modelWindow")
                    if modal.get_attribute("style") == "display: none;":
                        break
                except:
                    continue
                    
        except Exception as e:
            print(f"      ⚠️ Error closing modal: {str(e)}")
    
    def save_to_json(self, filename="pmc_services.json"):
        """Save scraped data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.services_data, f, indent=2, ensure_ascii=False)
        print(f"💾 Data saved to {filename}")
    
    def save_to_csv(self, filename="pmc_services.csv"):
        """Save scraped data to CSV file"""
        if not self.services_data:
            print("❌ No data to save")
            return
            
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['index', 'service_id', 'name', 'description', 'process', 'documents', 'fees']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for service in self.services_data:
                writer.writerow(service)
        
        print(f"💾 Data saved to {filename}")
    
    def display_summary(self):
        """Display a summary of scraped data"""
        if not self.services_data:
            print("❌ No services were scraped")
            return
            
        print(f"\n🎉 SCRAPING COMPLETED SUCCESSFULLY!")
        print(f"📊 Total services scraped: {len(self.services_data)}")
        
        # Count by department
        departments = {}
        for service in self.services_data:
            # Try to extract department from service name or ID
            dept = "Unknown Department"
            departments[dept] = departments.get(dept, 0) + 1
        
        print(f"\n📋 Sample of scraped services:")
        for i, service in enumerate(self.services_data[:5]):
            print(f"\n{i+1}. {service['name']}")
            print(f"   ID: {service['service_id']}")
            print(f"   Description: {service['description'][:100]}...")
            
        if len(self.services_data) > 5:
            print(f"\n... and {len(self.services_data) - 5} more services")
    
    def close(self):
        """Close the browser"""
        self.driver.quit()

def main():
    """Main function to run the scraper"""
    print("🏛️ PMC Services Scraper Starting...")
    
    # Create scraper instance
    scraper = PMCServicesScraper(headless=False)  # Set to True for headless mode
    
    try:
        # Scrape the services
        services = scraper.scrape_services()
        
        # Display results
        scraper.display_summary()
        
        # Save data in both formats
        scraper.save_to_json()
        scraper.save_to_csv()
        
    except KeyboardInterrupt:
        print("\n⏹️ Scraping interrupted by user")
    except Exception as e:
        print(f"💥 Scraping failed: {str(e)}")
    finally:
        scraper.close()
        print("🔚 Browser closed")

if __name__ == "__main__":
    main()