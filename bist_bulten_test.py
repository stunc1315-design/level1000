from pathlib import Path
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


# ============================================================
# BIST BÜLTEN İNDİRME TESTİ
# ============================================================

BASE = Path(r"D:\Level1000Web\turkiye_data\VARANT_VERI")
DOWNLOAD = BASE / "BULTENLER"

DOWNLOAD.mkdir(parents=True, exist_ok=True)

URL = "https://www.borsaistanbul.com/veriler/gunluk-bulten/gunluk-bulten-arsiv"


print("=" * 70)
print(" BIST BÜLTEN İNDİRME TESTİ")
print("=" * 70)


# ============================================================
# CHROME AYARLARI
# ============================================================

options = Options()

prefs = {
    "download.default_directory": str(DOWNLOAD.resolve()),
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True,
}

options.add_experimental_option(
    "prefs",
    prefs
)

options.add_argument("--start-maximized")


driver = webdriver.Chrome(options=options)


try:

    print()
    print("[1] BIST sayfası açılıyor...")

    driver.get(URL)

    time.sleep(5)

    print("[OK] Sayfa açıldı")
    print("Başlık:", driver.title)

    # ========================================================
    # TÜM INPUTLARI GÖSTER
    # ========================================================

    print()
    print("=" * 70)
    print("INPUTLAR")
    print("=" * 70)

    inputs = driver.find_elements(By.TAG_NAME, "input")

    for i, inp in enumerate(inputs):

        try:

            print(
                f"{i:02d} | "
                f"id={inp.get_attribute('id')} | "
                f"name={inp.get_attribute('name')} | "
                f"type={inp.get_attribute('type')} | "
                f"value={inp.get_attribute('value')}"
            )

        except:
            pass


    # ========================================================
    # TÜM BUTONLARI GÖSTER
    # ========================================================

    print()
    print("=" * 70)
    print("BUTONLAR")
    print("=" * 70)

    buttons = driver.find_elements(By.TAG_NAME, "button")

    for i, button in enumerate(buttons):

        try:

            text = button.text.strip()

            print(
                f"{i:02d} | "
                f"text={text!r} | "
                f"id={button.get_attribute('id')} | "
                f"class={button.get_attribute('class')}"
            )

        except:
            pass


    # ========================================================
    # "PAY PİYASASI BÜLTENLERİ" BUL
    # ========================================================

    print()
    print("=" * 70)
    print("PAY PİYASASI BÜLTENLERİ ARANIYOR")
    print("=" * 70)

    elements = driver.find_elements(
        By.XPATH,
        "//*[contains(normalize-space(.), 'Pay Piyasası Bültenleri')]"
    )

    print("Bulunan:", len(elements))


    for i, el in enumerate(elements[:10]):

        try:

            print()
            print("ELEMENT", i)
            print("TAG:", el.tag_name)
            print("TEXT:", el.text[:1000])

            print(
                "HTML:",
                el.get_attribute("outerHTML")[:5000]
            )

        except:
            pass


    # ========================================================
    # SAYFANIN HTML'İNİ KAYDET
    # ========================================================

    html_path = BASE / "bist_selenium.html"

    html_path.write_text(
        driver.page_source,
        encoding="utf-8"
    )

    print()
    print("[HTML KAYDEDİLDİ]")
    print(html_path)


    # ========================================================
    # EKRAN GÖRÜNTÜSÜ
    # ========================================================

    screenshot = BASE / "bist_selenium.png"

    driver.save_screenshot(
        str(screenshot)
    )

    print("[SCREENSHOT]")
    print(screenshot)


    # ========================================================
    # İNDİRME KLASÖRÜ
    # ========================================================

    print()
    print("=" * 70)
    print("İNDİRME KLASÖRÜ")
    print("=" * 70)

    print(DOWNLOAD)

    print()
    print("Chrome açık bırakılıyor.")
    print("İnceleme tamamlandı.")


    # Kapanmasın
    input(
        "\nKapatmak için ENTER'a bas..."
    )


finally:

    driver.quit()


print()
print("=" * 70)
print("TAMAMLANDI")
print("=" * 70)