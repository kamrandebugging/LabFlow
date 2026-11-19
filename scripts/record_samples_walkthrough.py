import os
import time
import subprocess
import shutil
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

FRAMES_DIR = "M:/LabFlow/screenshots/samples/frames"
VIDEO_OUT = "M:/LabFlow/screenshots/samples/samples_veyla_walkthrough.mp4"
BRAIN_VIDEO = "C:/Users/CodeNexus/.gemini/antigravity/brain/23477e46-8369-49ec-9aef-a8eed9fc4417/samples_veyla_walkthrough.mp4"

os.makedirs(FRAMES_DIR, exist_ok=True)

# Clean old frames
for f in os.listdir(FRAMES_DIR):
    if f.endswith(".png"):
        os.remove(os.path.join(FRAMES_DIR, f))

options = Options()
options.add_argument("--headless=new")
options.add_argument("--window-size=1440,960")
options.add_argument("--force-device-scale-factor=1")

driver = webdriver.Chrome(options=options)
frame_idx = 0

def snap(repeat=1):
    global frame_idx
    for _ in range(repeat):
        frame_idx += 1
        path = os.path.join(FRAMES_DIR, f"frame_{frame_idx:04d}.png")
        driver.save_screenshot(path)

try:
    print("Logging in for walkthrough...")
    driver.get("http://demo-lhr.localhost:5173/login")
    time.sleep(1)
    driver.find_element(By.ID, "email").send_keys("technician@demo-lhr.com")
    driver.find_element(By.ID, "password").send_keys("TechDemoPass2026!")
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(2)

    # Dismiss post-login notice if present
    try:
        dialog_btns = driver.find_elements(By.CSS_SELECTOR, "div[role='alertdialog'] button, [role='dialog'] button")
        for btn in dialog_btns:
            driver.execute_script("arguments[0].click();", btn)
        time.sleep(1)
    except Exception:
        pass

    # 1. Samples List (Light)
    print("Walkthrough: Samples List (Light)")
    driver.get("http://demo-lhr.localhost:5173/samples")
    time.sleep(1.5)
    # Dismiss notice if still on screen
    try:
        dialog_btns = driver.find_elements(By.CSS_SELECTOR, "div[role='alertdialog'] button, [role='dialog'] button")
        for btn in dialog_btns:
            driver.execute_script("arguments[0].click();", btn)
        time.sleep(0.5)
    except Exception:
        pass

    snap(15)  # 1.5 seconds

    # Switch to All Samples Tab
    tabs = driver.find_elements(By.CSS_SELECTOR, "button[role='tab']")
    for t in tabs:
        if "All samples" in t.text:
            driver.execute_script("arguments[0].click();", t)
            break
    time.sleep(1)
    snap(15)

    # Select samples to reveal Bulk Bar
    checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
    if len(checkboxes) > 1:
        driver.execute_script("arguments[0].click();", checkboxes[1])
        if len(checkboxes) > 2:
            driver.execute_script("arguments[0].click();", checkboxes[2])
    time.sleep(1)
    snap(15)  # Shows floating bulk bar

    # Theme Toggle to Dark
    print("Walkthrough: Theme Toggle to Dark")
    driver.execute_script("document.documentElement.classList.add('dark'); localStorage.setItem('theme', 'dark');")
    time.sleep(0.5)
    snap(15)

    # 2. Collect Step 1
    print("Walkthrough: Collect Step 1")
    driver.get("http://demo-lhr.localhost:5173/samples/collect/step1")
    time.sleep(1.5)
    snap(15)

    # 3. Collect Step 2
    print("Walkthrough: Collect Step 2")
    driver.get("http://demo-lhr.localhost:5173/samples/collect/step2")
    time.sleep(1.5)
    snap(15)

    # 4. Sample Detail
    print("Walkthrough: Sample Detail")
    driver.get("http://demo-lhr.localhost:5173/samples/f56b6e86-d70a-40ee-b7bd-0d223b4464c7")
    time.sleep(1.5)
    snap(20)

    # 5. Sample Label
    print("Walkthrough: Sample Label")
    driver.get("http://demo-lhr.localhost:5173/samples/f56b6e86-d70a-40ee-b7bd-0d223b4464c7/label")
    time.sleep(1.5)
    snap(20)

    # Switch back to light
    driver.execute_script("document.documentElement.classList.remove('dark'); localStorage.setItem('theme', 'light');")
    time.sleep(0.5)
    snap(15)

    print(f"Captured {frame_idx} frames. Compiling MP4 video with ffmpeg...")

finally:
    driver.quit()

# Compile with ffmpeg at 10 fps
cmd = [
    "ffmpeg", "-y",
    "-framerate", "10",
    "-i", os.path.join(FRAMES_DIR, "frame_%04d.png"),
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "-vf", "scale=1440:960",
    VIDEO_OUT
]
subprocess.run(cmd, check=True)
shutil.copy2(VIDEO_OUT, BRAIN_VIDEO)
print("Video successfully generated at:", VIDEO_OUT)
