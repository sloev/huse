import requests
import json
import os
import math
import time
from datetime import datetime

# Configuration
DESTINATION_COORDS = (10.50257979, 55.06919914) # Ollerup Bytorv 4
DESTINATION_NAME = "Ollerup Bytorv 4"
MAX_BUS_MINUTES = 40
MAX_COMMUTE_WALK_BIKE = 12 # Max mins spent on bike/walk to/from bus or destination
MAX_TOTAL_MINUTES = 40 
MAX_PRICE = 900000
MIN_ROOMS = 3

# Speeds in km/h
WALK_SPEED = 5
BIKE_SPEED = 15

# BUS 800A Stops & Travel time to Ollerup Bytorv (minutes)
BUS_800A_STOPS = [
    {"name": "Gudme", "coords": (10.704, 55.148), "bus_time": 35},
    {"name": "Oure", "coords": (10.709, 55.123), "bus_time": 30},
    {"name": "Vejstrup", "coords": (10.707, 55.101), "bus_time": 25},
    {"name": "Skårup", "coords": (10.686, 55.093), "bus_time": 20},
    {"name": "Svendborg Station", "coords": (10.611, 55.059), "bus_time": 15},
    {"name": "Hvidkilde", "coords": (10.535, 55.074), "bus_time": 5},
    {"name": "Ollerup Bytorv", "coords": (10.502, 55.069), "bus_time": 0},
    {"name": "Vester Skerninge", "coords": (10.457, 55.074), "bus_time": 5},
    {"name": "Ulbølle", "coords": (10.422, 55.075), "bus_time": 10},
    {"name": "Faaborg Plads", "coords": (10.244, 55.097), "bus_time": 30},
]

# Svendborg & Faaborg-Midtfyn Postal Codes
POSTAL_CODES = [
    "5700", "5762", "5771", "5874", "5881", "5882", "5883", "5884", "5892", # Svendborg
    "5600", "5642", "5672", "5750", "5772", "5792", "5854", "5856", "5863" # Faaborg-Midtfyn
]

DATA_FILE = "houses.json"

def haversine_distance(coord1, coord2):
    lon1, lat1 = coord1
    lon2, lat2 = coord2
    R = 6371 
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) * math.sin(dlat / 2) + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon / 2) * math.sin(dlon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_commute(house_coords):
    # 1. Direct travel
    dist_direct = haversine_distance(house_coords, DESTINATION_COORDS)
    walk_direct = (dist_direct / WALK_SPEED) * 60
    bike_direct = (dist_direct / BIKE_SPEED) * 60
    
    if walk_direct <= MAX_COMMUTE_WALK_BIKE and walk_direct <= MAX_TOTAL_MINUTES:
        return {"mode": "Walking", "duration": int(walk_direct), "line": "Direct"}
    if bike_direct <= MAX_COMMUTE_WALK_BIKE and bike_direct <= MAX_TOTAL_MINUTES:
        return {"mode": "Biking", "duration": int(bike_direct), "line": "Direct"}
    
    # 2. Bus travel
    best_commute = None
    for stop in BUS_800A_STOPS:
        if stop['bus_time'] > MAX_BUS_MINUTES:
            continue
        dist_to_stop = haversine_distance(house_coords, stop['coords'])
        walk_to_stop = (dist_to_stop / WALK_SPEED) * 60
        bike_to_stop = (dist_to_stop / BIKE_SPEED) * 60
        
        # Walk to stop
        if walk_to_stop <= MAX_COMMUTE_WALK_BIKE:
            tw = walk_to_stop + stop['bus_time']
            if tw <= MAX_TOTAL_MINUTES:
                if not best_commute or tw < best_commute['duration']:
                    best_commute = {"mode": "Walk + Bus", "duration": int(tw), "line": f"800A via {stop['name']}"}
        
        # Bike to stop
        if bike_to_stop <= MAX_COMMUTE_WALK_BIKE:
            tb = bike_to_stop + stop['bus_time']
            if tb <= MAX_TOTAL_MINUTES:
                if not best_commute or tb < best_commute['duration']:
                    best_commute = {"mode": "Bike + Bus", "duration": int(tb), "line": f"800A via {stop['name']}"}
                
    return best_commute

def scrape_boliga():
    houses = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for zip_code in POSTAL_CODES:
        print(f"Scraping ZIP {zip_code}...")
        url = f"https://api.boliga.dk/api/v2/search/results?zipCodes={zip_code}&pageSize=200&priceMax={MAX_PRICE}"
        try:
            res = requests.get(url, headers=headers)
            results = res.json().get('results', [])
            print(f"  Found {len(results)} items under {MAX_PRICE} DKK")
            
            for item in results:
                rooms = item.get('rooms')
                if rooms is None or rooms < MIN_ROOMS:
                    continue

                lat = item.get('latitude')
                lon = item.get('longitude')
                
                if not lat or not lon:
                    continue
                
                coords = (lon, lat)
                commute = calculate_commute(coords)
                
                if commute:
                    img_url = ""
                    if item.get('images'):
                        img_url = item['images'][0].get('url', '')
                    
                    addr_str = f"{item.get('street')} {item.get('houseNumber') or ''}, {item.get('zipCode')} {item.get('city')}"
                    
                    houses.append({
                        "id": item.get('id'),
                        "address": addr_str,
                        "price": item.get('price', 0),
                        "size": item.get('size', 0),
                        "rooms": rooms,
                        "lotSize": item.get('lotSize', 0),
                        "energyRating": item.get('energyClass'),
                        "link": f"https://www.boliga.dk/bolig/{item.get('id')}",
                        "commute": commute,
                        "image": img_url or f"https://images.boliga.dk/storage/properties/actual/{item.get('id')}/1",
                        "isForeclosure": item.get('isForeclosure', False)
                    })
                    print(f"    VALID: {addr_str} ({commute['duration']}m, {rooms} rooms)")
                
        except Exception as e:
            print(f"  Error: {e}")
            
    return houses

def main():
    valid_houses = scrape_boliga()
    # Deduplicate by ID
    unique_houses = {h['id']: h for h in valid_houses}.values()
    
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(unique_houses), f, ensure_ascii=False, indent=2)
    print(f"Finished. Saved {len(unique_houses)} houses.")

if __name__ == "__main__":
    main()
