import time
import urllib.parse
import requests
import os
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

NTFY_TOPIC_URL = "https://ntfy.sh/tu_canal_secreto_wallapop"
JSON_FILENAME = "wallapop_anuncios.json"
MAX_CLICKS_LOAD_MORE = 5

def build_wallapop_search_url(
    keywords="", category_id="100", brand="", model="", # Cambiado category_ids a category_id
    min_km="", max_km="", min_year="", max_year="",
    gearbox="", seller_type="", engine="",
    source="search_box", country_code="ES",
    latitude="", longitude="",
    min_sale_price="", max_sale_price="",
    time_filter="", 
    distance_in_km="" # Cambiado distance_in_km a distance_in_km (valor en km)
):
    """
    Construye la URL de búsqueda para Wallapop con los parámetros dados.
    Incluye filtros de ubicación, precio y tiempo.
    """
    params = {
        'keywords': keywords, 'category_id': category_id, 'brand': brand, # Cambiado category_ids a category_id
        'model': model, 'min_km': min_km, 'max_km': max_km,
        'min_year': min_year, 'max_year': max_year, 'gearbox': gearbox,
        'seller_type': seller_type, 'engine': engine, 'source': source,
        'country_code': country_code,
        'latitude': latitude, 'longitude': longitude,
        'min_sale_price': min_sale_price, 'max_sale_price': max_sale_price,
        'time_filter': time_filter
    }
    
    # Añadir distancia en metros si se proporciona distance_in_km
    if distance_in_km and str(distance_in_km).strip().isdigit():
        params['distance'] = int(str(distance_in_km).strip()) * 1000

    filtered_params = {k: v for k, v in params.items() if v is not None and str(v).strip() != ""}
    query_string = urllib.parse.urlencode(filtered_params)
    base_url = "https://es.wallapop.com/app/search" 
    return f"{base_url}?{query_string}"

def send_ntfy_notification(title, message, priority="default"):
    if not NTFY_TOPIC_URL or "tu_canal_secreto" in NTFY_TOPIC_URL:
        print("ADVERTENCIA: NTFY_TOPIC_URL no está configurado o usa el valor por defecto. No se enviarán notificaciones.")
        return
    try:
        headers = {
            "Title": title.encode('utf-8'),
            "Priority": priority,
            "Tags": "car,wallapop"
        }
        response = requests.post(NTFY_TOPIC_URL, data=message.encode('utf-8'), headers=headers)
        if response.status_code == 200:
            print(f"Notificación enviada a ntfy.sh: {title}")
        else:
            print(f"Error enviando notificación a ntfy.sh (código {response.status_code}): {response.text}")
    except Exception as e:
        print(f"Excepción enviando notificación a ntfy.sh: {e}")

def load_existing_listings_from_json(filename=JSON_FILENAME):
    existing_data_map = {}
    existing_urls_set = set()
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                if os.path.getsize(filename) == 0:
                    print(f"Advertencia: El archivo JSON '{filename}' está vacío. Se tratará como si no existiera.")
                    return {}, set()

                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and 'url' in item:
                            existing_data_map[item['url']] = item
                            existing_urls_set.add(item['url'])
            print(f"Cargados {len(existing_urls_set)} anuncios existentes desde '{filename}'.")
        except json.JSONDecodeError:
            print(f"Error: El archivo '{filename}' no es un JSON válido. Se creará uno nuevo si es necesario.")
        except Exception as e:
            print(f"Error cargando datos desde el archivo JSON '{filename}': {e}")
    return existing_data_map, existing_urls_set

def save_listings_to_json(all_current_listings_map, filename=JSON_FILENAME):
    if not all_current_listings_map:
        if not os.path.exists(filename):
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump([], f)
                print(f"Archivo JSON '{filename}' creado vacío (no había datos para guardar).")
            except Exception as e:
                print(f"Error creando archivo JSON vacío '{filename}': {e}")
        else:
            print("No hay datos nuevos o actualizados para guardar en JSON, el archivo existente no se modifica.")
        return

    list_to_save = list(all_current_listings_map.values())
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(list_to_save, f, ensure_ascii=False, indent=4, default=str)
        print(f"Archivo JSON '{filename}' guardado/actualizado con {len(list_to_save)} anuncios.")
    except Exception as e:
        print(f"Error guardando en el archivo JSON '{filename}': {e}")

def scrape_current_page_listings(driver):
    current_page_listings = []
    try:
        WebDriverWait(driver, 10).until( # Aumentado ligeramente el wait por si acaso
             EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.ItemCardList a.ItemCardList__item"))
        )
        item_elements = driver.find_elements(By.CSS_SELECTOR, "div.ItemCardList a.ItemCardList__item")
        if not item_elements: 
            print("No se encontraron elementos 'ItemCardList__item'.")
            return []

        for item_element in item_elements:
            title, price, url, image_url = "No disponible", "No disponible", "No disponible", "No disponible"
            try:
                try:
                    title_p_element = item_element.find_element(By.CSS_SELECTOR, "p.ItemCard__title")
                    title = title_p_element.text.strip()
                except NoSuchElementException:
                    title_attr = item_element.get_attribute('title')
                    if title_attr: title = title_attr.strip()

                try: 
                    price_element = item_element.find_element(By.CSS_SELECTOR, "span.ItemCard__price")
                    price = price_element.text.strip()
                except NoSuchElementException: 
                    # print(f"  Precio no encontrado con 'span.ItemCard__price' para el item con título (aprox): {title[:30]}")
                    pass
                
                href_attr = item_element.get_attribute('href')
                if href_attr:
                    url = href_attr
                    if not url.startswith("http"): url = urllib.parse.urljoin("https://es.wallapop.com", url)
                
                try:
                    img_element = item_element.find_element(By.CSS_SELECTOR, "div.ItemCard__image img")
                    img_src = img_element.get_attribute('src')
                    if img_src: image_url = img_src
                except NoSuchElementException:
                    # print(f"  Imagen no encontrada con 'div.ItemCard__image img' para el item con título (aprox): {title[:30]}")
                    pass

                if url != "No disponible":
                    current_page_listings.append({
                        "title": title, "price": price, "url": url, "image_url": image_url,
                        "timestamp_seen": datetime.now().isoformat()
                    })
            except Exception as e_item: print(f"  Error menor procesando un sub-elemento de item: {e_item}")
        return current_page_listings
    except TimeoutException: print("Timeout esperando los items de la página actual."); return []
    except Exception as e_page: print(f"Error grave extrayendo items de la página actual: {e_page}"); return []

def scrape_all_listings_with_load_more(driver):
    all_fetched_listings = []
    seen_urls_in_current_run = set()
    clicks = 0
    no_new_items_streak = 0

    while clicks < MAX_CLICKS_LOAD_MORE:
        print(f"Extrayendo anuncios (intento de carga #{clicks + 1})...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(4) # Aumentar un poco por si hay lazy loading que afecte a los selectores

        current_page_items = scrape_current_page_listings(driver)
        newly_added_this_iteration = 0
        if current_page_items:
            for item_data in current_page_items:
                if item_data['url'] not in seen_urls_in_current_run:
                    all_fetched_listings.append(item_data)
                    seen_urls_in_current_run.add(item_data['url'])
                    newly_added_this_iteration += 1
            print(f"Se añadieron {newly_added_this_iteration} anuncios únicos a la lista de esta ejecución.")
        else:
            print("No se encontraron items en la vista actual de la página en este intento.")

        if newly_added_this_iteration == 0 and clicks > 0 : # Solo contar racha si ya hubo clics previos
            no_new_items_streak += 1
            if no_new_items_streak >= 2:
                 print("No se encontraron más anuncios nuevos tras varios intentos con 'Cargar más'. Finalizando carga.")
                 break
        elif newly_added_this_iteration > 0 :
            no_new_items_streak = 0

        try:
            load_more_button_xpath = "//walla-button[@text='Cargar más' and not(@disabled)] | //button[contains(., 'Cargar más') and not(@disabled)]"
            WebDriverWait(driver, 7).until(EC.presence_of_element_located((By.XPATH, load_more_button_xpath))) # Solo presencia
            load_more_button = driver.find_element(By.XPATH, load_more_button_xpath)
            
            # Scroll hasta el botón y luego un poco más para asegurar visibilidad y clickeabilidad
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", load_more_button)
            time.sleep(0.5)
            driver.execute_script("window.scrollBy(0, 150);") # Scroll un poco más para evitar que esté tapado
            time.sleep(0.5)

            # Esperar a que sea clickeable
            load_more_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, load_more_button_xpath)))
            print("Botón 'Cargar más' encontrado y clickeable. Haciendo clic...")
            # driver.execute_script("arguments[0].click();", load_more_button) # Click con JS
            load_more_button.click() # Click directo de Selenium
            
            clicks += 1
            print("Esperando carga de nuevos items...")
            time.sleep(5) 
        except TimeoutException:
            print("No se encontró el botón 'Cargar más' (o no es clickeable/visible). Asumiendo fin de resultados.")
            break
        except Exception as e:
            print(f"Error al intentar clickear 'Cargar más': {e}")
            break
            
    print(f"Total de anuncios únicos extraídos en esta ejecución después de {clicks} clics en 'Cargar más': {len(all_fetched_listings)}")
    return all_fetched_listings

def run_scraper(search_params, send_notifications=True, headless_mode=False):
    final_url = build_wallapop_search_url(**search_params)
    print(f"\n--- Iniciando Scraper ---")
    print(f"Modo Notificaciones: {'Activado' if send_notifications else 'Desactivado (Inicialización)'}")
    print(f"Modo Headless: {'Activado' if headless_mode else 'Desactivado'}")
    print(f"URL de Búsqueda: {final_url}\n")

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    if headless_mode:
        options.add_argument('--headless=new') 
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")

    print("Inicializando Selenium WebDriver...")
    driver = None
    try:
        try:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e_driver_manager:
            print(f"Error con ChromeDriverManager: {e_driver_manager}")
            print("Intentando con el ChromeDriver por defecto en PATH si existe...")
            driver = webdriver.Chrome(options=options)

    except Exception as e:
        print(f"Error Crítico al inicializar ChromeDriver: {e}"); return

    try:
        print(f"Abriendo URL...")
        driver.get(final_url)
        time.sleep(5) # Aumentar espera inicial

        try:
            cookie_button = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            )
            cookie_button.click()
            print("Cookies aceptadas.")
            time.sleep(2) 
        except TimeoutException:
            print("Botón de cookies no encontrado tras la espera (puede que no sea necesario o ya esté aceptado).")
        except Exception as e_cookie:
            print(f"Error al intentar aceptar cookies: {e_cookie}")

        print(f"\nTítulo de la página: {driver.title}")

        existing_data_map, existing_urls_set = load_existing_listings_from_json(JSON_FILENAME)
        all_listings_data_from_web = scrape_all_listings_with_load_more(driver)

        if not all_listings_data_from_web:
            print("No se extrajeron anuncios de la web en esta ejecución.")
            save_listings_to_json(existing_data_map, JSON_FILENAME)
        else:
            print(f"\nTotal de {len(all_listings_data_from_web)} anuncios únicos extraídos de la web.")
            
            new_listings_for_notification = []
            updated_data_map = existing_data_map.copy() 

            for web_listing in all_listings_data_from_web:
                url = web_listing['url']
                if url not in existing_urls_set: 
                    new_listings_for_notification.append(web_listing)
                updated_data_map[url] = web_listing 

            if send_notifications:
                if new_listings_for_notification:
                    print(f"\n--- {len(new_listings_for_notification)} Anuncios Nuevos Encontrados para Notificación ---")
                    for new_listing in new_listings_for_notification:
                        title_notif = f"Nuevo Wallapop: {new_listing['title'][:50]}"
                        message_notif = f"Precio: {new_listing['price']}\n{new_listing['url']}"
                        send_ntfy_notification(title_notif, message_notif, priority="high")
                        time.sleep(1) 
                else:
                    print("\nNo hay anuncios nuevos para notificar (comparado con el JSON existente).")
            else: 
                print("\nModo de inicialización/Notificaciones desactivadas.")
                if new_listings_for_notification:
                     print(f"Se habrían notificado {len(new_listings_for_notification)} anuncios si las notificaciones estuvieran activas.")

            save_listings_to_json(updated_data_map, JSON_FILENAME)

        print("\nEjecución del scraper completada.")
        time.sleep(3)

    except Exception as e:
        print(f"Error principal durante la ejecución del scraper: {e}")
        import traceback
        traceback.print_exc() 
    finally:
        print("Cerrando el navegador...")
        if driver:
            driver.quit()
        print("Navegador cerrado.")


def main():
    search_config = {
        "keywords": "toyota corolla 180H", 
        "category_id": "100", # Cambiado category_ids a category_id
         "brand": "Toyota", 
         "model": "Corolla", 
         "min_year": "2019", 
         "max_year": "2024", 
        # "engine": "gasoline", 
        # "min_km": "20000", 
        # "max_km": "90000", 

        "distance_in_km": "333", # Cambiado distance_in_km a distance_in_km (valor en km)
        "latitude": "40.96882", 
        "longitude": "-5.66388", 
        
        "min_sale_price": "12000", 
        "max_sale_price": "22000", 
        "time_filter": "lastWeek", 
        
        "source": "search_box", 
        "country_code": "ES" 
    }

    MODO_INICIALIZACION = True
    MODO_HEADLESS = False


    if MODO_INICIALIZACION:
        print("Ejecutando en modo de inicialización (SIN notificaciones)...")
        run_scraper(search_params=search_config, send_notifications=False, headless_mode=MODO_HEADLESS)
    else:
        print("Ejecutando en modo normal (con notificaciones para nuevos items)...")
        run_scraper(search_params=search_config, send_notifications=True, headless_mode=MODO_HEADLESS)


if __name__ == "__main__":
    main()