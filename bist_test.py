# ============================================================
# BIST GERÇEK BÜLTEN BLOĞUNU BUL
# ============================================================

from pathlib import Path
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


BASE_DIR = Path(r"D:\Level1000Web")

URL = "https://www.borsaistanbul.com/veriler/gunluk-bulten/gunluk-bulten-arsiv"


# ============================================================
# CHROME
# ============================================================

options = Options()

driver = webdriver.Chrome(options=options)

driver.get(URL)

time.sleep(5)


print("=" * 80)
print(" BIST GERÇEK BÜLTEN BLOĞU ANALİZİ")
print("=" * 80)

print("\nSayfa:", driver.title)


# ============================================================
# PAY PİYASASI METNİNİ BUL
# ============================================================

print("\n[1] Pay Piyasası Bültenleri aranıyor...")

elements = driver.find_elements(
    By.XPATH,
    "//*[normalize-space(text())='Pay Piyasası Bültenleri']"
)

print("Bulunan:", len(elements))


if not elements:

    print("\n[HATA] Tam eşleşme bulunamadı.")

    # Daha gevşek arama
    elements = driver.find_elements(
        By.XPATH,
        "//*[contains(normalize-space(text()), 'Pay Piyasası Bültenleri')]"
    )

    print("Gevşek arama:", len(elements))


# ============================================================
# HER BULUNAN ELEMENTİN PARENTLERİNİ YAZ
# ============================================================

for no, el in enumerate(elements):

    print("\n")
    print("=" * 80)
    print(f" ELEMENT {no}")
    print("=" * 80)

    try:

        print("\nELEMENT HTML:")
        print(el.get_attribute("outerHTML")[:5000])

    except Exception as e:
        print("HTML hata:", e)


    parent = el

    for level in range(1, 9):

        try:

            parent = parent.find_element(By.XPATH, "..")

            print("\n")
            print("-" * 80)
            print(f"PARENT SEVIYE {level}")
            print("-" * 80)

            html = parent.get_attribute("outerHTML")

            print(html[:15000])

        except Exception as e:

            print("Parent hata:", e)
            break


# ============================================================
# TÜM INPUTLARI YAZ
# ============================================================

print("\n")
print("=" * 80)
print(" TÜM INPUTLAR")
print("=" * 80)

inputs = driver.find_elements(By.TAG_NAME, "input")

for i, inp in enumerate(inputs):

    try:

        print(
            f"""
INPUT {i}
 type        = {inp.get_attribute("type")}
 id          = {inp.get_attribute("id")}
 name        = {inp.get_attribute("name")}
 class       = {inp.get_attribute("class")}
 value       = {inp.get_attribute("value")}
 placeholder = {inp.get_attribute("placeholder")}
 """
        )

    except:
        pass


# ============================================================
# TÜM BUTTONLAR
# ============================================================

print("\n")
print("=" * 80)
print(" TÜM BUTTONLAR")
print("=" * 80)

buttons = driver.find_elements(By.TAG_NAME, "button")

for i, btn in enumerate(buttons):

    try:

        print(
            f"""
BUTTON {i}
 text   = {btn.text!r}
 id     = {btn.get_attribute("id")}
 name   = {btn.get_attribute("name")}
 type   = {btn.get_attribute("type")}
 class  = {btn.get_attribute("class")}
 onclick= {btn.get_attribute("onclick")}
 """
        )

    except:
        pass


# ============================================================
# TÜM ANCHORLAR
# ============================================================

print("\n")
print("=" * 80)
print(" TÜM LINKLER")
print("=" * 80)

links = driver.find_elements(By.TAG_NAME, "a")

for i, link in enumerate(links):

    try:

        text = link.text.strip()
        href = link.get_attribute("href")
        onclick = link.get_attribute("onclick")
        download = link.get_attribute("download")

        if (
            text
            or href
            or onclick
            or download
        ):

            print(
                f"""
LINK {i}
 text     = {text!r}
 href     = {href}
 onclick  = {onclick}
 download = {download}
 """
            )

    except:
        pass


# ============================================================
# HTML'İ DOSYAYA DA KAYDET
# ============================================================

try:

    html_file = BASE_DIR / "bist_sayfa.html"

    html_file.write_text(
        driver.page_source,
        encoding="utf-8"
    )

    print("\nHTML kaydedildi:")
    print(html_file)

except Exception as e:

    print("HTML kaydedilemedi:", e)


# ============================================================
# EKRAN GÖRÜNTÜSÜ
# ============================================================

try:

    screenshot = BASE_DIR / "bist_debug2.png"

    driver.save_screenshot(str(screenshot))

    print("\nScreenshot:")
    print(screenshot)

except Exception as e:

    print("Screenshot hata:", e)


# ============================================================
# SON
# ============================================================

print("\n")
print("=" * 80)
print(" ANALİZ TAMAMLANDI")
print("=" * 80)

print("""
BU ÇIKTIYI BURAYA AT.

Özellikle:

ELEMENT HTML
PARENT SEVIYE 1
PARENT SEVIYE 2
...
INPUTLAR
BUTTONLAR
LINKLER

kısımları önemli.
""")

input("\nKapatmak için ENTER...")

driver.quit()