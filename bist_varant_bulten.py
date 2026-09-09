# ============================================================
# BIST TÜM VARANTLAR - BIST BÜLTEN OTOMATİK İNDİRİCİ
# ============================================================
#
# AMAÇ:
# Borsa İstanbul Günlük Bülten Arşivinden
# Pay Piyasası Bültenlerini otomatik indirir.
#
# Sonra indirilen dosyalardan varantları ayıklar.
#
# ÇIKTI:
# D:\Level1000Web\turkiye_data\BIST_TUM_VARANTLAR.csv
#
# ============================================================

import sys
import subprocess
import re
import time
import os
import shutil
from pathlib import Path
from datetime import date, timedelta


# ============================================================
# GEREKLİ PAKETLER
# ============================================================

def install_package(package, import_name=None):

    if import_name is None:
        import_name = package

    try:
        __import__(import_name)
    except ImportError:

        print()
        print(f"[KURULUYOR] {package}")

        subprocess.check_call([
            sys.executable,
            "-m",
            "pip",
            "install",
            package
        ])


install_package("selenium")


# ============================================================
# IMPORT
# ============================================================

import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ============================================================
# AYARLAR
# ============================================================

BASE_DIR = Path(r"D:\Level1000Web")

DATA_DIR = BASE_DIR / "turkiye_data"

DOWNLOAD_DIR = DATA_DIR / "BIST_BULTENLER"

OUTPUT_FILE = DATA_DIR / "BIST_TUM_VARANTLAR.csv"

DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True
)


BIST_URL = (
    "https://www.borsaistanbul.com/"
    "veriler/gunluk-bulten/"
    "gunluk-bulten-arsiv"
)


# ============================================================
# TARİH AYARLARI
# ============================================================
#
# BIST'in kendi arşivinde 30.11.2015 sonrası tarihsel
# veriler DataStore üzerinden tutuluyor.
#
# Burada başlangıç olarak 30.11.2015'ten bugüne kadar
# tarama hazırlanıyor.
#
# İstersen daha sonra sadece belirli dönemleri de taratabiliriz.
# ============================================================

START_DATE = date(2015, 11, 30)

END_DATE = date.today()


# ============================================================
# CHROME AYARLARI
# ============================================================

print()
print("=" * 80)
print(" BIST TÜM VARANTLAR - BÜLTEN TARAMA")
print("=" * 80)
print()

print("BIST bülten arşivi hazırlanıyor...")
print()

chrome_options = Options()

chrome_options.add_argument(
    "--start-maximized"
)

chrome_options.add_argument(
    "--disable-blink-features=AutomationControlled"
)

chrome_options.add_argument(
    "--disable-notifications"
)

chrome_options.add_experimental_option(
    "prefs",
    {
        "download.default_directory": str(
            DOWNLOAD_DIR.resolve()
        ),

        "download.prompt_for_download": False,

        "download.directory_upgrade": True,

        "safebrowsing.enabled": True
    }
)


# ============================================================
# CHROME
# ============================================================

try:

    driver = webdriver.Chrome(
        options=chrome_options
    )

except Exception as e:

    print()
    print("=" * 80)
    print(" CHROME BAŞLATILAMADI")
    print("=" * 80)
    print()
    print(e)
    print()
    print("Chrome kurulu olduğundan emin ol.")
    print()
    input("Kapatmak için ENTER...")
    sys.exit(1)


wait = WebDriverWait(
    driver,
    30
)


# ============================================================
# YARDIMCI
# ============================================================

def clean_old_downloads():

    print("[TEMİZLİK] Eski bülten dosyaları kontrol ediliyor...")

    for p in DOWNLOAD_DIR.iterdir():

        try:

            if p.is_file():

                p.unlink()

        except Exception:
            pass


def wait_download(timeout=30):

    """
    Chrome'un yeni dosya indirmesini bekler.
    """

    start = time.time()

    old_files = set(
        p.name
        for p in DOWNLOAD_DIR.iterdir()
        if p.is_file()
    )

    while time.time() - start < timeout:

        time.sleep(1)

        current_files = set(
            p.name
            for p in DOWNLOAD_DIR.iterdir()
            if p.is_file()
        )

        new_files = current_files - old_files

        valid = []

        for name in new_files:

            lower = name.lower()

            if (
                lower.endswith(".csv")
                or lower.endswith(".zip")
                or lower.endswith(".xlsx")
                or lower.endswith(".xls")
                or lower.endswith(".txt")
            ):

                if not lower.endswith(".crdownload"):

                    valid.append(
                        DOWNLOAD_DIR / name
                    )

        if valid:

            return valid[0]

    return None


# ============================================================
# BIST SAYFASI
# ============================================================

print("[BIST] Sayfa açılıyor...")

driver.get(BIST_URL)

time.sleep(5)

print(
    "[BIST] Sayfa:",
    driver.title
)

print()


# ============================================================
# SAYFADAKİ INPUTLARI GÖSTER
# ============================================================

inputs = driver.find_elements(
    By.TAG_NAME,
    "input"
)

print(
    f"[BIST] Input sayısı: {len(inputs)}"
)

for i, element in enumerate(inputs):

    try:

        print(
            f"  INPUT {i}: "
            f"type={element.get_attribute('type')} "
            f"name={element.get_attribute('name')} "
            f"id={element.get_attribute('id')} "
            f"value={element.get_attribute('value')}"
        )

    except Exception:
        pass


print()


# ============================================================
# BUTONLARI GÖSTER
# ============================================================

buttons = driver.find_elements(
    By.TAG_NAME,
    "button"
)

print(
    f"[BIST] Button sayısı: {len(buttons)}"
)

for i, button in enumerate(buttons):

    try:

        txt = (
            button.text
            or
            button.get_attribute("aria-label")
            or
            ""
        )

        if txt.strip():

            print(
                f"  BUTTON {i}: {txt.strip()}"
            )

    except Exception:
        pass


print()


# ============================================================
# PAY PİYASASI BÜLTENİ BUL
# ============================================================

print(
    "[BIST] Pay Piyasası Bültenleri aranıyor..."
)


# Sayfadaki bütün elementleri kontrol ediyoruz.

elements = driver.find_elements(
    By.XPATH,
    "//*[contains("
    "translate(normalize-space(.),"
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZÇĞİÖŞÜ',"
    "'abcdefghijklmnopqrstuvwxyzçğıöşü'),"
    "'pay piyasası bültenleri'"
    ")]"
)


print(
    f"[BIST] Bulunan element: {len(elements)}"
)

print()


target = None


for element in elements:

    try:

        text = element.text.strip()

        if (
            "Pay Piyasası Bültenleri"
            in text
        ):

            target = element

            print(
                "[BIST] Hedef bulundu:"
            )

            print(
                text[:500]
            )

            break

    except Exception:
        pass


# ============================================================
# HEDEF YOKSA
# ============================================================

if target is None:

    print()
    print("=" * 80)
    print(" PAY PİYASASI BÜLTENİ BULUNAMADI")
    print("=" * 80)
    print()
    print(
        "BIST sayfasının HTML yapısı değişmiş olabilir."
    )
    print()
    print(
        "Chrome açık bırakıldı."
    )
    print()
    input(
        "İncelemek için ENTER..."
    )

    driver.quit()

    sys.exit(1)


# ============================================================
# YAKIN INPUT BUL
# ============================================================

print()
print(
    "[BIST] Tarih alanı aranıyor..."
)


# Hedef elementin yakınındaki inputları bul.

parent = target

found_input = None
found_button = None


for level in range(8):

    try:

        parent = parent.find_element(
            By.XPATH,
            ".."
        )

        local_inputs = parent.find_elements(
            By.TAG_NAME,
            "input"
        )

        local_buttons = parent.find_elements(
            By.TAG_NAME,
            "button"
        )

        local_links = parent.find_elements(
            By.TAG_NAME,
            "a"
        )

        if local_inputs:

            found_input = local_inputs[-1]

        if local_buttons:

            found_button = local_buttons[-1]

        if (
            found_input is not None
            and
            (
                found_button is not None
                or
                local_links
            )
        ):

            break

    except Exception:
        break


# ============================================================
# TARİH INPUT
# ============================================================

if found_input:

    print(
        "[BIST] Tarih inputu bulundu:"
    )

    print(
        " type =",
        found_input.get_attribute("type")
    )

    print(
        " name =",
        found_input.get_attribute("name")
    )

    print(
        " id =",
        found_input.get_attribute("id")
    )

else:

    print(
        "[UYARI] Tarih inputu otomatik bulunamadı."
    )


# ============================================================
# İLK TEST
# ============================================================

print()
print(
    "[BIST] Bugünün bülteni test ediliyor..."
)


def set_input_value(element, value):

    try:

        driver.execute_script(
            """
            arguments[0].value = arguments[1];

            arguments[0].dispatchEvent(
                new Event('input', { bubbles: true })
            );

            arguments[0].dispatchEvent(
                new Event('change', { bubbles: true })
            );
            """,
            element,
            value
        )

        return True

    except Exception:

        return False


# ============================================================
# BUTON TIKLAMA
# ============================================================

def click_near_target():

    # Önce button

    if found_button:

        try:

            driver.execute_script(
                "arguments[0].click();",
                found_button
            )

            return True

        except Exception:
            pass


    # Sonra link

    try:

        links = parent.find_elements(
            By.TAG_NAME,
            "a"
        )

        for link in links:

            txt = (
                link.text
                or
                link.get_attribute(
                    "title"
                )
                or
                ""
            )

            href = (
                link.get_attribute(
                    "href"
                )
                or
                ""
            )

            if (
                "bülten" in txt.lower()
                or
                "download" in href.lower()
                or
                "file" in href.lower()
            ):

                driver.execute_script(
                    "arguments[0].click();",
                    link
                )

                return True

    except Exception:
        pass


    return False


# ============================================================
# TEST
# ============================================================

if found_input:

    today_text = END_DATE.strftime(
        "%d.%m.%Y"
    )

    print(
        "[BIST] Tarih:",
        today_text
    )

    set_input_value(
        found_input,
        today_text
    )


clicked = click_near_target()


if clicked:

    print(
        "[BIST] Bülten butonuna tıklandı."
    )

else:

    print(
        "[UYARI] Buton otomatik tıklanamadı."
    )


time.sleep(5)


# ============================================================
# İNDİRİLEN DOSYA
# ============================================================

downloaded = wait_download(
    timeout=15
)


if downloaded:

    print()
    print(
        "[BAŞARILI] Bülten indirildi:"
    )

    print(
        downloaded
    )

else:

    print()
    print(
        "[BİLGİ] İlk testte otomatik dosya bulunamadı."
    )


# ============================================================
# SAYFADAKİ TÜM DOWNLOAD LINKLERİNİ TARA
# ============================================================

print()
print(
    "[BIST] Sayfadaki indirme bağlantıları taranıyor..."
)


links = driver.find_elements(
    By.TAG_NAME,
    "a"
)

download_links = []


for link in links:

    try:

        href = (
            link.get_attribute("href")
            or
            ""
        )

        text = (
            link.text
            or
            ""
        )

        low = (
            href + " " + text
        ).lower()

        if any(
            x in low
            for x in [
                ".csv",
                ".zip",
                ".xlsx",
                ".xls",
                ".txt",
                "download",
                "bulten",
                "bülten"
            ]
        ):

            download_links.append(
                (
                    text.strip(),
                    href
                )
            )

    except Exception:
        pass


print(
    f"[BIST] Potansiyel link: "
    f"{len(download_links)}"
)

print()


for i, (text, href) in enumerate(
    download_links[:30],
    1
):

    print(
        f"{i:3d}. {text[:60]} "
        f"{href[:120]}"
    )


# ============================================================
# SONUÇ
# ============================================================

print()
print("=" * 80)
print(" BIST BÜLTEN TESTİ TAMAMLANDI")
print("=" * 80)
print()

print(
    "İndirilen klasör:"
)

print(
    DOWNLOAD_DIR
)

print()

print(
    "Bu aşamada Chrome açık kalıyor."
)

print(
    "Eğer BIST bülten butonu düzgün çalıştıysa"
)

print(
    "dosya yukarıdaki klasöre inecek."
)

print()

input(
    "Kontrol ettikten sonra ENTER'a bas..."
)

driver.quit()