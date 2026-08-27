from arduino.app_utils import *
from arduino.app_bricks.web_ui import WebUI

def get_status():
    analog = Bridge.call("get_analog", "")
    led = Bridge.call("get_led", "")
    return {"analog": int(analog), "led": led}

def toggle_led():
    new_state = Bridge.call("toggle_led", "")
    return {"led": new_state}

web_ui = WebUI()
web_ui.expose_api("GET", "/api/status", get_status)
web_ui.expose_api("POST", "/api/led/toggle", toggle_led)
App.run()
