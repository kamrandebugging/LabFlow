import os
import time
import shutil
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

OUTPUT_DIR = "M:/LabFlow/screenshots/samples"
BRAIN_DIR = "C:/Users/CodeNexus/.gemini/antigravity/brain/23477e46-8369-49ec-9aef-a8eed9fc4417/screenshots"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(BRAIN_DIR, exist_ok=True)

options = Options()
options.add_argument("--headless=new")
options.add_argument("--window-size=1440,960")
options.add_argument("--force-device-scale-factor=1")

driver = webdriver.Chrome(options=options)

try:
    print("Navigating to login page...")
    driver.get("http://demo-lhr.localhost:5173/login")
    time.sleep(2)

    # 1. Fill credentials
    email_el = driver.find_element(By.ID, "email")
    email_el.clear()
    email_el.send_keys("technician@demo-lhr.com")

    pw_el = driver.find_element(By.ID, "password")
    pw_el.clear()
    pw_el.send_keys("TechDemoPass2026!")

    submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    submit_btn.click()
    time.sleep(3)
    print("Logged in, current URL:", driver.current_url)

    def set_theme(theme: str):
        if theme == "dark":
            driver.execute_script("document.documentElement.classList.add('dark'); localStorage.setItem('theme', 'dark');")
        else:
            driver.execute_script("document.documentElement.classList.remove('dark'); localStorage.setItem('theme', 'light');")
        time.sleep(0.5)

    def save_screen(name: str, theme: str):
        filename = f"{name}_{theme}.png"
        path_local = os.path.join(OUTPUT_DIR, filename)
        path_brain = os.path.join(BRAIN_DIR, filename)
        driver.save_screenshot(path_local)
        shutil.copy2(path_local, path_brain)
        print(f"Captured: {filename}")

    # SCREEN 1: Samples List (/samples)
    print("Capturing Screen 1: Samples List...")
    driver.get("http://demo-lhr.localhost:5173/samples")
    time.sleep(2)
    set_theme("light")
    save_screen("01_samples_list", "light")
    set_theme("dark")
    save_screen("01_samples_list", "dark")

    # SCREEN 2: Collect Sample Step 1 (/samples/collect/step1)
    print("Capturing Screen 2: Collect Step 1...")
    driver.get("http://demo-lhr.localhost:5173/samples/collect/step1")
    time.sleep(2)
    set_theme("light")
    save_screen("02_collect_step1", "light")
    set_theme("dark")
    save_screen("02_collect_step1", "dark")

    # SCREEN 3: Collect Sample Step 2 (/samples/collect/step2)
    print("Capturing Screen 3: Collect Step 2...")
    driver.get("http://demo-lhr.localhost:5173/samples/collect/step2")
    time.sleep(2)
    set_theme("light")
    save_screen("03_collect_step2", "light")
    set_theme("dark")
    save_screen("03_collect_step2", "dark")

    # SCREEN 4: Sample Detail (/samples/:id)
    # Use existing sample f56b6e86-d70a-40ee-b7bd-0d223b4464c7
    print("Capturing Screen 4: Sample Detail...")
    driver.get("http://demo-lhr.localhost:5173/samples/f56b6e86-d70a-40ee-b7bd-0d223b4464c7")
    time.sleep(2)
    set_theme("light")
    save_screen("04_sample_detail", "light")
    set_theme("dark")
    save_screen("04_sample_detail", "dark")

    # SCREEN 5: Sample Label (/samples/:id/label)
    print("Capturing Screen 5: Sample Label...")
    driver.get("http://demo-lhr.localhost:5173/samples/f56b6e86-d70a-40ee-b7bd-0d223b4464c7/label")
    time.sleep(2)
    set_theme("light")
    save_screen("05_sample_label", "light")
    set_theme("dark")
    save_screen("05_sample_label", "dark")

    print("ALL 10 SCREENSHOTS CAPTURED SUCCESSFULLY!")

finally:
    driver.quit()
