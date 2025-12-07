import os
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from markdownify import markdownify as md

import sys

def setup_driver():
    # Force UTF-8 for stdout to avoid cp949 errors on Windows
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    options = webdriver.ChromeOptions()
    # options.add_argument('--headless') # Run in headless mode if desired
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def crawl_ekgwb():
    driver = setup_driver()
    base_url = "http://www.nietzschesource.org/#eKGWB"
    
    sections_to_crawl = [
        {"name": "Published Works", "type": "flat"},
        {"name": "Private Publications", "type": "flat"},
        {"name": "Authorized Manuscripts", "type": "flat"},
        {"name": "Posthumous Writings", "type": "flat"},
        {"name": "Posthumous Fragments", "type": "nested"},
        {"name": "Letters", "type": "nested"},
    ]
    
    try:
        print(f"Navigating to {base_url}...")
        driver.get(base_url)
        wait = WebDriverWait(driver, 10)
        
        # Ensure the page is loaded
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))

        for section in sections_to_crawl:
            section_name = section['name']
            section_type = section['type']
            
            print(f"\n--- Processing Section: {section_name} ---")
            
            try:
                # 1. Click the section header to expand it
                # Using XPath to find the link with the specific text
                section_link = wait.until(EC.element_to_be_clickable((By.XPATH, f"//a[contains(text(), '{section_name}')]")))
                section_link.click()
                print(f"Expanded '{section_name}'.")
                time.sleep(2) # Wait for animation/load
                
                books_to_crawl = []
                
                # 2. Identify books based on section type
                if section_type == "flat":
                    # For flat sections, books are direct children (a.nlink)
                    # We look for links that look like books (have data-book attribute) 
                    # strictly speaking, we might need to be careful not to pick up other things,
                    # but usually, just looking at the menu structure is enough.
                    # A safe bet is to look for links that are visible and have data-book.
                    
                    # We re-query the DOM to ensure staleness doesn't affect us
                    # This selector finds all book links under the actively expanded sections
                    # However, since we just clicked one, we should try to narrow it down if possible.
                    # But the site structure puts them in a simple list. 
                    # We can iterate all visible book links and filter by ID if needed, 
                    # but simpler is to grab *all* visible links that look like books.
                    
                    # Let's target the links that are currently visible in the menu
                    menu_links = driver.find_elements(By.CSS_SELECTOR, "ul.book a.nlink")
                    
                    for link in menu_links:
                        if not link.is_displayed():
                            continue
                            
                        # Check if this link belongs to the section we want. 
                        # Without a strict hierarchy in the DOM (it might be flat lists), 
                        # we might pick up books from other expanded sections if we are not careful.
                        # But we are clicking strictly one by one.
                        # Assuming the previous click collapses others or we just look for *new* things?
                        # Actually, eKGWB usually keeps things expanded. 
                        # So we should be careful. 
                        # The "Published Works" IDs usually start with eKGWB/
                        
                        # A better approach given the DOM structure (flat list in sidebar?):
                        # The sidebar usually highlights the active selection.
                        
                        # Let's try to grab the specific container if possible, OR
                        # Just grab all visible links and filter by some heuristic if needed.
                        # For now, let's trust that clicking the section makes its children visible
                        # and we can iterate them.
                        
                        data_book = link.get_attribute('data-book')
                        title = link.text
                        
                        if data_book and '#eKGWB/' in data_book:
                            # Heuristic: Check if it's likely part of this section.
                            # Published Works -> eKGWB/GT, etc.
                            # This might capture Everything if everything is expanded.
                            # So we might want to close other sections or just be permissive and rely on deduplication.
                            
                            # Let's just collect it. We handle deduplication later.
                            books_to_crawl.append({'title': title, 'id': data_book.replace('#', '')})

                elif section_type == "nested":
                    # For nested sections, we iterate all visible links in the scroll area
                    # and filter by data-book or text pattern depending on the section.
                    
                    # We wait a bit for the menu to populate
                    time.sleep(1)
                    
                    # Find all potential links. 
                    # The test showed they are in div#scroll but maybe purely finding by text pattern is safer
                    # or just iterating all visible interactions.
                    
                    menu_links = driver.find_elements(By.CSS_SELECTOR, "div#scroll a.nlink")
                    
                    for link in menu_links:
                        if not link.is_displayed():
                            continue
                            
                        title = link.text
                        data_book = link.get_attribute('data-book')
                        
                        # Check if it matches our expectation for this section
                        is_valid = False
                        book_id = None
                        
                        if data_book and "#eKGWB/" in data_book:
                             temp_id = data_book.replace('#', '')
                             
                             if section_name == "Letters" and "BVN-" in temp_id:
                                 is_valid = True
                                 book_id = temp_id
                             elif section_name == "Posthumous Fragments" and "NF-" in temp_id:
                                 # Note: The ID usually looks like eKGWB/NF-1869-1
                                 is_valid = True
                                 book_id = temp_id
                        
                        if is_valid and book_id:
                            books_to_crawl.append({'title': title, 'id': book_id})

                print(f"Found {len(books_to_crawl)} items in {section_name}.")
                
                # Create section directory
                section_dir = os.path.join("output", section_name)
                if not os.path.exists(section_dir):
                    os.makedirs(section_dir)
                    
                for book in books_to_crawl:
                    title = book['title']
                    book_id = book['id']
                    
                    # Sanitize title for filename
                    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
                    # Also remove very long text if title is huge
                    if len(safe_title) > 100:
                        safe_title = safe_title[:100]
                        
                    output_path = os.path.join(section_dir, f"{safe_title}.md")
                    
                    if os.path.exists(output_path):
                        # print(f"Skipping {title}, already exists.")
                        continue
                        
                    try:
                        print(f"Processing: {title} ({book_id})")
                    except Exception:
                        safe_print_title = title.encode('ascii', 'ignore').decode('ascii')
                        print(f"Processing: {safe_print_title} ({book_id})")
                    
                    print_url = f"http://www.nietzschesource.org/{book_id}/print"
                    
                    # print(f"  Navigating to print view: {print_url}")
                    driver.get(print_url)
                    
                    # Wait for content to load
                    try:
                        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                        # Additional wait for specific content to ensure it's not a 404/empty
                        # e.g. check for a div with class 'text' or just wait a bit
                        time.sleep(2)
                    except Exception as e:
                        print(f"  Error loading page for {book_id}: {e}")
                        continue
                    
                    content_html = driver.page_source
                    markdown_text = md(content_html)
                    
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(markdown_text)
                    
                    print(f"  Saved to {output_path}")
                    time.sleep(0.5)

            except Exception as e:
                print(f"Error processing section {section_name}: {e}")
                # Continue to next section
                continue

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    crawl_ekgwb()
