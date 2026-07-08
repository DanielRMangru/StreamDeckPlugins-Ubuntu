import io
import time
import json
import urllib.request
import threading
from PIL import Image, ImageDraw, ImageFont
from plugin_base import BasePlugin

def get_wmo_description(code):
    # WMO Weather interpretation codes (WW)
    if code == 0:
        return "Clear", (245, 158, 11)  # Amber Sun
    elif code in (1, 2, 3):
        return "Cloudy", (156, 163, 175) # Gray Cloud
    elif code in (45, 48):
        return "Foggy", (100, 116, 139)
    elif code in (51, 53, 55, 56, 57):
        return "Drizzle", (96, 165, 250)
    elif code in (61, 63, 65, 66, 67):
        return "Rainy", (59, 130, 246)   # Blue Rain
    elif code in (71, 73, 75, 77):
        return "Snowy", (248, 250, 252)  # White Snow
    elif code in (80, 81, 82):
        return "Showers", (37, 99, 235)
    elif code in (95, 96, 99):
        return "Storm", (124, 58, 237)   # Purple Thunder
    return "Weather", (156, 163, 175)

def get_aqi_description(aqi):
    if aqi <= 50:
        return "Good", (34, 197, 94)      # Green
    elif aqi <= 100:
        return "Moderate", (234, 179, 8)  # Yellow
    elif aqi <= 150:
        return "Sensitive", (249, 115, 22) # Orange
    elif aqi <= 200:
        return "Unhealthy", (239, 68, 68)  # Red
    return "Hazardous", (185, 28, 28)

class WeatherPollenPlugin(BasePlugin):
    name = "Weather & Pollen"
    description = "Displays live local weather. Press key or tap screen to toggle Pollen / Air Quality info."
    author = "System"
    version = "1.0.0"
    target = "both"
    
    def __init__(self, settings: dict = None):
        super().__init__(settings)
        self.mode = "weather" # "weather" or "allergy"
        self.city = "Loading..."
        self.temp = 0.0
        self.weather_code = 0
        self.aqi = 0
        self.pollen_summary = "Pollen: Low"
        self.running = True
        self.redraw_callback = None
        
        # Start background polling thread (every 15 minutes)
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        
    def cleanup(self):
        self.running = False
        
    def _fetch_data(self):
        try:
            # 1. Geolocation
            req = urllib.request.Request('https://freeipapi.com/api/json', headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                geo = json.loads(response.read().decode())
            lat = geo.get('latitude', 38.5816)
            lon = geo.get('longitude', -121.494)
            self.city = geo.get('cityName', 'Local')
            
            # 2. Current Weather
            weather_url = f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&temperature_unit=fahrenheit'
            with urllib.request.urlopen(weather_url) as response:
                weather = json.loads(response.read().decode())
            self.temp = weather['current']['temperature_2m']
            self.weather_code = weather['current']['weather_code']
            
            # 3. Air Quality & Pollen
            aq_url = f'https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=us_aqi,alder_pollen,birch_pollen,grass_pollen,ragweed_pollen'
            with urllib.request.urlopen(aq_url) as response:
                aq = json.loads(response.read().decode())
                
            curr_aq = aq['current']
            self.aqi = curr_aq.get('us_aqi', 0)
            
            # Formulate pollen summary
            pollen_types = ['grass_pollen', 'birch_pollen', 'ragweed_pollen']
            active_pollen = []
            for t in pollen_types:
                val = curr_aq.get(t)
                if val is not None and val > 0:
                    name = t.split('_')[0].capitalize()
                    active_pollen.append(f"{name}: {int(val)}")
            
            if active_pollen:
                self.pollen_summary = ", ".join(active_pollen[:2])
            else:
                # Fallback to AQI based status
                if self.aqi <= 50:
                    self.pollen_summary = "Pollen: Negligible"
                else:
                    self.pollen_summary = "Air: Moderate"
                    
            print(f"[WEATHER] Updated. City: {self.city}, Temp: {self.temp}°F, AQI: {self.aqi}")
        except Exception as e:
            print(f"[WEATHER] Error fetching weather data: {e}")
            self.city = "API Offline"
            
    def _poll_loop(self):
        while self.running:
            self._fetch_data()
            if self.redraw_callback:
                self.redraw_callback()
            # Sleep 15 minutes (900s)
            for _ in range(900):
                if not self.running:
                    break
                time.sleep(1)
                
    def get_image(self, state: str) -> bytes:
        img = Image.new("RGB", (120, 120), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)
        draw.rectangle([3, 3, 116, 116], outline=(30, 41, 59), width=2)
        
        try:
            font_title = ImageFont.load_default(size=11)
            font_val = ImageFont.load_default(size=24)
            font_lbl = ImageFont.load_default(size=13)
            font_city = ImageFont.load_default(size=12)
        except Exception:
            font_title = font_val = font_lbl = font_city = ImageFont.load_default()
            
        if self.mode == "weather":
            # --- Weather Mode ---
            desc, color = get_wmo_description(self.weather_code)
            
            # Draw Header Badge
            bbox = draw.textbbox((0, 0), "WEATHER", font=font_title)
            draw.text(((120 - (bbox[2] - bbox[0])) // 2, 15), "WEATHER", fill=(59, 130, 246), font=font_title)
            
            # Temp
            temp_str = f"{int(self.temp)}°F"
            bbox = draw.textbbox((0, 0), temp_str, font=font_val)
            draw.text(((120 - (bbox[2] - bbox[0])) // 2, 42), temp_str, fill=(255, 255, 255), font=font_val)
            
            # Weather description label
            bbox = draw.textbbox((0, 0), desc, font=font_lbl)
            draw.text(((120 - (bbox[2] - bbox[0])) // 2, 74), desc, fill=color, font=font_lbl)
            
            # City Label at the bottom
            city_str = self.city[:14]
            bbox = draw.textbbox((0, 0), city_str, font=font_city)
            draw.text(((120 - (bbox[2] - bbox[0])) // 2, 95), city_str, fill=(148, 163, 184), font=font_city)
        else:
            # --- Pollen / Allergy Mode ---
            aqi_desc, color = get_aqi_description(self.aqi)
            
            # Header
            bbox = draw.textbbox((0, 0), "ALLERGY/AQI", font=font_title)
            draw.text(((120 - (bbox[2] - bbox[0])) // 2, 15), "ALLERGY/AQI", fill=(168, 85, 247), font=font_title)
            
            # AQI Value
            aqi_str = f"{self.aqi}"
            bbox = draw.textbbox((0, 0), aqi_str, font=font_val)
            draw.text(((120 - (bbox[2] - bbox[0])) // 2, 42), aqi_str, fill=(255, 255, 255), font=font_val)
            
            # AQI rating label
            bbox = draw.textbbox((0, 0), aqi_desc, font=font_lbl)
            draw.text(((120 - (bbox[2] - bbox[0])) // 2, 74), aqi_desc, fill=color, font=font_lbl)
            
            # Brief pollen/air text at bottom
            pollen_str = self.pollen_summary.split(',')[0][:15] # Just show first pollen metric
            bbox = draw.textbbox((0, 0), pollen_str, font=font_city)
            draw.text(((120 - (bbox[2] - bbox[0])) // 2, 95), pollen_str, fill=(148, 163, 184), font=font_city)
            
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
        
    def draw_segment(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        draw.rectangle([0, 0, width, height], fill=(20, 20, 20))
        
        try:
            font_title = ImageFont.load_default(size=13)
            font_val = ImageFont.load_default(size=15)
            font_small = ImageFont.load_default(size=11)
        except Exception:
            font_title = font_val = font_small = ImageFont.load_default()
            
        # Draw combined information on the dial screen
        desc, weather_color = get_wmo_description(self.weather_code)
        aqi_desc, aqi_color = get_aqi_description(self.aqi)
        
        if self.mode == "weather":
            draw.text((15, 10), f"WEATHER - {self.city[:12].upper()}", fill=(150, 150, 150), font=font_title)
            val_str = f"{self.temp:.1f}°F  ({desc})"
            draw.text((15, 30), val_str, fill=(255, 255, 255), font=font_val)
            
            # Progress bar for temp (14 to 113F range mapping)
            pct = max(0.0, min(1.0, (self.temp - 14) / 99.0))
            draw.rectangle([15, 65, 185, 77], fill=(40, 40, 40))
            fill_w = int(170 * pct)
            if fill_w > 0:
                draw.rectangle([15, 65, 15 + fill_w, 77], fill=weather_color)
        else:
            draw.text((15, 10), "AIR QUALITY & POLLEN", fill=(150, 150, 150), font=font_title)
            val_str = f"AQI: {self.aqi}  ({aqi_desc})"
            draw.text((15, 30), val_str, fill=(255, 255, 255), font=font_val)
            
            # Progress bar for AQI (0 to 300 range mapping)
            pct = max(0.0, min(1.0, self.aqi / 300.0))
            draw.rectangle([15, 65, 185, 77], fill=(40, 40, 40))
            fill_w = int(170 * pct)
            if fill_w > 0:
                draw.rectangle([15, 65, 15 + fill_w, 77], fill=aqi_color)
                
        # Draw pollen details at the bottom left if space permits, or tap hint
        draw.text((15, height - 18), self.pollen_summary[:28], fill=(100, 116, 139), font=font_small)
        draw.text((width - 52, height - 16), "[ tap ]", fill=(55, 55, 55), font=font_small)
        
    def on_press(self):
        self.toggle_mode()
        
    def on_touch(self, event_type, value: dict, deck):
        if event_type == 1 or event_type == "SHORT" or getattr(event_type, "name", "") == "SHORT":
            self.toggle_mode()
            
    def toggle_mode(self):
        self.mode = "allergy" if self.mode == "weather" else "weather"
        print(f"[WEATHER] Toggled display mode to: {self.mode}")
