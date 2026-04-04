import csv
import requests
REQUEST_TIMEOUT = 5 

def harvest_images(csv_filepath):
    with open(csv_filepath, mode='r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            uid = row.get('uid')
            name = row.get('name')
            base_url = row.get('website_url')
            base_url = base_url.rstrip('/')
            image_url = f"https://{base_url}/images/pfp.jpg"
            print(f"Attempting to fetch image for {name} ({uid}) at {image_url}...")
            try:
                
                response = requests.get(image_url, timeout=REQUEST_TIMEOUT)
                
                if response.status_code == 200:
                    print(f"✅ Success! Image downloaded for {uid}.")
                    
                    image_binary_data = response.content 
                    
                    # TODO: Insert user metadata (uid, name, elo=1200) into MySQL
                    # TODO: Upsert image_binary_data into MongoDB
                    
                elif response.status_code == 404:
                    print(f"❌ HTTP 404: Image not found for {uid}. Skipping...")
                else:
                    print(f"⚠️ HTTP {response.status_code}: Failed to fetch for {uid}. Skipping...")
                    
            except requests.exceptions.Timeout:
                print(f"⚠️ Timeout: Connection took too long for {uid}. Skipping...")
            except requests.exceptions.ConnectionError:
                print(f"⚠️ Connection Error: Could not reach the server for {uid}. Skipping...")
            except requests.exceptions.RequestException as e:
                # Catches any other requests-related errors so the script doesn't crash
                print(f"⚠️ An unexpected network error occurred for {uid}: {e}. Skipping...")
if __name__ == "__main__":
    harvest_images('batch_data.csv')