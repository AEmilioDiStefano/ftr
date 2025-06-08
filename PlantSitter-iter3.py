# PlantSitter uses a state machine desing to run two state machines 
# simultaneously - one for air temperature control and another for 
# soil humidity control. 
#
#------------------------------------------------------------------
# Change History
#------------------------------------------------------------------
# Version   |   Description
#------------------------------------------------------------------
#    1          Initial Development
#------------------------------------------------------------------

##
## This import is used for timing in the main loop
##
from time import sleep
from datetime import datetime 

import tracemalloc

import asyncio
from reduct import Client, Bucket
from datetime import datetime
import random

##
## This import is used for Python 'multithreading'
##
import threading

##
## These imports allow us to build a fully functional state machine
##
from statemachine import StateMachine, State

##
## Imports necessary to provide connectivity to the 
## thermostat sensor and the I2C bus
##
import board
##import adafruit_ahtx0
import adafruit_sht31d

############################################################
########## FIXME: Find the appropriate library    ##########
########## for the temperature sensor.            ##########
############################################################

##
## These are the packages that we need to pull in so that we can work
## with the GPIO interface on the Raspberry Pi board and work with
## the 16x2 LCD display
##
# import board - already imported for I2C connectivity
import digitalio
import adafruit_character_lcd.character_lcd as characterlcd

## This imports the Python serial package to handle communications over the
## Raspberry Pi's serial port. 
import serial

##
## Imports required to handle our Button, and our PWMLED devices
##
from gpiozero import Button, PWMLED

##
## This package is necessary so that we can delegate the blinking
## lights to their own thread so that more work can be done at the
## same time
##
from threading import Thread

##
## This is needed to get coherent matching of temperatures.
##
from math import floor

##
## DEBUG flag - boolean value to indicate whether or not to print 
## status messages on the console of the program
## 
DEBUG = True

##
## Create an I2C instance so that we can communicate with
## devices on the I2C bus.
##
i2c = board.I2C()

##
## Initialize our Temperature and Humidity sensor.
## Toggle between the following two thSensor 
## variable definitions depending on whether you 
## are using an AHTx0 or SHT31 temperature sensor.
##

#thSensor = adafruit_ahtx0.AHTx0(i2c)

thSensor = adafruit_sht31d.SHT31D(i2c)

##
## Initialize our serial connection
##
## Because we imported the entire package instead of just importing Serial and
## some of the other flags from the serial package, we need to reference those
## objects with dot notation.
##
## e.g. ser = serial.Serial
##
ser = serial.Serial(
        port='/dev/ttyS0', # This would be /dev/ttyAM0 prior to Raspberry Pi 3
        baudrate = 115200, # This sets the speed of the serial interface in
                           # bits/second
        parity=serial.PARITY_NONE,      # Disable parity
        stopbits=serial.STOPBITS_ONE,   # Serial protocol will use one stop bit
        bytesize=serial.EIGHTBITS,      # We are using 8-bit bytes 
        timeout=1          # Configure a 1-second timeout
)

##
## Our four LEDs:
## GPIO 18
## GPIO 23
## GPIO 21
## GPIO 20
##
redLight = PWMLED(18)
blueLight = PWMLED(23)
yellowLight = PWMLED(21)
greenLight = PWMLED(20)

##
## ManagedDisplay - Class intended to manage the 16x2 
## Display
##
## This code is largely taken from the work done in module 4, and
## converted into a class so that we can more easily consume the 
## operational capabilities.
##
class ManagedTemperatureDisplay():
    ##
    ## Class Initialization method to setup the display
    ##
    def __init__(self):
        ##
        ## Setup the six GPIO lines to communicate with the display.
        ## This leverages the digitalio class to handle digital 
        ## outputs on the GPIO lines. There is also an analagous
        ## class for analog IO.
        ##
        ## You need to make sure that the port mappings match the
        ## physical wiring of the display interface to the 
        ## GPIO interface.
        ##
        ## compatible with all versions of RPI as of Jan. 2019
        ##
        self.lcd_rs = digitalio.DigitalInOut(board.D17)
        self.lcd_en = digitalio.DigitalInOut(board.D8)
        self.lcd_d4 = digitalio.DigitalInOut(board.D5)
        self.lcd_d5 = digitalio.DigitalInOut(board.D6)
        self.lcd_d6 = digitalio.DigitalInOut(board.D13)
        self.lcd_d7 = digitalio.DigitalInOut(board.D26)

        # Modify this if you have a different sized character LCD
        self.lcd_columns = 16
        self.lcd_rows = 2 

        # Initialise the lcd class
        self.lcd = characterlcd.Character_LCD_Mono(self.lcd_rs, self.lcd_en, 
                    self.lcd_d4, self.lcd_d5, self.lcd_d6, self.lcd_d7, 
                    self.lcd_columns, self.lcd_rows)

        # wipe LCD screen before we start
        self.lcd.clear()

class ManagedHumidityDisplay():
    ##
    ## Class Initialization method to setup the display
    ##
    def __init__(self):
        ##
        ## Setup the six GPIO lines to communicate with the display.
        ## This leverages the digitalio class to handle digital 
        ## outputs on the GPIO lines. There is also an analagous
        ## class for analog IO.
        ##
        ## You need to make sure that the port mappings match the
        ## physical wiring of the display interface to the 
        ## GPIO interface.
        ##
        ## compatible with all versions of RPI as of Jan. 2019
        ##
        self.lcd_rs = digitalio.DigitalInOut(board.D17)
        self.lcd_en = digitalio.DigitalInOut(board.D7)
        self.lcd_d4 = digitalio.DigitalInOut(board.D5)
        self.lcd_d5 = digitalio.DigitalInOut(board.D6)
        self.lcd_d6 = digitalio.DigitalInOut(board.D13)
        self.lcd_d7 = digitalio.DigitalInOut(board.D26)

        # Modify this if you have a different sized character LCD
        self.lcd_columns = 16
        self.lcd_rows = 2 

        # Initialise the lcd class
        self.lcd = characterlcd.Character_LCD_Mono(self.lcd_rs, self.lcd_en, 
                    self.lcd_d4, self.lcd_d5, self.lcd_d6, self.lcd_d7, 
                    self.lcd_columns, self.lcd_rows)

        # wipe LCD screen before we start
        self.lcd.clear()

    ##
    ## cleanupDisplay - Method used to cleanup the digitalIO lines that
    ## are used to run the display.
    ##
    def cleanupDisplay(self):
        # Clear the LCD first - otherwise we won't be abe to update it.
        self.lcd.clear()
        self.lcd_rs.deinit()
        self.lcd_en.deinit()
        self.lcd_d4.deinit()
        self.lcd_d5.deinit()
        self.lcd_d6.deinit()
        self.lcd_d7.deinit()
        
    ##
    ## clear - Convenience method used to clear the display
    ##
    def clear(self):
        self.lcd.clear()

    ##
    ## updateScreen - Convenience method used to update the message.
    ##
    def updateScreen(self, message):
        self.lcd.clear()
        self.lcd.message = message

    ## End class ManagedDisplay definition  

##
## Initialize our displays
##
temperature_screen = ManagedTemperatureDisplay()
humidity_screen = ManagedHumidityDisplay()

####################################################################################################################
####################################################################################################################
####################################################################################################################
#####  _______                                  _                  __  __            _     _              ##########
##### |__   __|                                | |                |  \/  |          | |   (_)             ##########
#####    | | ___ _ __ ___  _ __   ___ _ __ __ _| |_ _   _ _ __ ___| \  / | __ _  ___| |__  _ _ __   ___   ##########
#####    | |/ _ \ '_ ` _ \| '_ \ / _ \ '__/ _` | __| | | | '__/ _ \ |\/| |/ _` |/ __| '_ \| | '_ \ / _ \  ##########
#####    | |  __/ | | | | | |_) |  __/ | | (_| | |_| |_| | | |  __/ |  | | (_| | (__| | | | | | | |  __/  ##########
#####    |_|\___|_| |_| |_| .__/ \___|_|  \__,_|\__|\__,_|_|  \___|_|  |_|\__,_|\___|_| |_|_|_| |_|\___|  ##########
#####                     | |                                                                             ##########
#####                     |_|                                                                             ##########
#####                                                                                                     ##########
####################################################################################################################
####################################################################################################################
####################################################################################################################

##
## TemperatureMachine - This is our StateMachine implementation class.
## The purpose of this state machine is to manage the states
## handled by our thermostat:
##
##  off
##  heat
##  cool
##
##
class TemperatureMachine(StateMachine):
    "A state machine designed to manage the temperature"

    ##
    ## Define the three states for our machine.
    ##
    ##  off - nothing lit up
    ##  red - only red LED fading in and out
    ##  blue - only blue LED fading in and out
    ##
    off = State(initial = True)
    heat = State()
    cool = State()

    ##
    ## Default temperature setPoint is 72 degrees Fahrenheit
    ##
    setPoint = 72

    ##
    ## These variables enable a safety feature which 
    ## sets a maximum and minimum target temperature
    ##
    maxSetPoint = 95
    minSetPoint = 60


    ##
    ## cycle - event that provides the state machine behavior
    ## of transitioning between the three states of our 
    ## thermostat
    ##
    cycle = (
        off.to(heat) |
        heat.to(cool) |
        cool.to(off)
    )

    cycle_heat_to_cool = (
        heat.to(cool)
    )

    cycle_cool_to_heat = (
        cool.to(heat)
    )

    cycle_cool_to_off = (
        cool.to(off)
    )

    cycle_off_to_heat = (
        off.to(heat)
    )

    cycle_off_to_cool = (
        off.to(cool)
    )

    ##
    ## on_enter_heat - Action performed when the state machine transitions
    ## into the 'heat' state
    ##
    def on_enter_heat(self):
        ##
        ## Pulse the red indicator light upon entering 
        ## the 'heat' state. 
        redLight.pulse()

        if(DEBUG):
            print("* Changing state to heat")

    ##
    ## on_exit_heat - Action performed when the statemachine transitions
    ## out of the 'heat' state.
    ##
    def on_exit_heat(self):
        ##
        ## Turn off the red indicator light upon exiting 
        ## the heat state.
        redLight.off()

    ##
    ## on_enter_cool - Action performed when the state machine transitions
    ## into the 'cool' state
    ##
    def on_enter_cool(self):
        ##
        ## Pulse the blue indicator light upon entering 
        ## the 'cool' state.
        blueLight.pulse()

        if(DEBUG):
            print("* Changing state to cool")

    ##
    ## on_exit_cool - Action performed when the statemachine transitions
    ## out of the 'cool' state.
    ##
    def on_exit_cool(self):
        ##
        ## Turn off the blue indicator light upon exiting 
        ## the 'cool' state.
        blueLight.off()

    ##
    ## on_enter_off - Action performed when the state machine transitions
    ## into the 'off' state
    ##
    def on_enter_off(self):
        ##
        ## Turn off all lights upon entering the off state.
        redLight.off()
        blueLight.off()

        if(DEBUG):
            print("* Changing state to off")

   ##
    ## processTempIncButton - Utility method used to update the 
    ## setPoint for the temperature. This will increase the setPoint
    ## by a single degree. This is triggered by the button_pressed event
    ## handler for our second button
    ##
    def processTempIncButton(self):

        if(DEBUG):
            print("Increasing Set Point (Temperature)")

        ##
        ## Update the setPoint of the thermostat and the status lights
        ## within the circuit.
        # If the setPoint is less than the maximum set point, 
        if (self.setPoint < self.maxSetPoint):
            # then increment the setPoint by 1
            self.setPoint = self.setPoint + 1

    ##
    ## processTempDecButton - Utility method used to update the 
    ## setPoint for the temperature. This will decrease the setPoint
    ## by a single degree. This is triggered by the button_pressed event
    ## handler for our third button
    ##

    def processTempDecButton(self):

        if(DEBUG):
            print("Decreasing Set Point (Temperature)")

        ##
        ## Update the setPoint of the thermostat and the status lights
        ## within the circuit.
        # If the setPoint is greater than the minimum set point,
        if (self.setPoint > self.minSetPoint):
            # then decrease the set point by 1
            self.setPoint = self.setPoint - 1

    ##
    ## updateDB - this method updates our database with a timestamped temperature reading
    ##
    async def updateDB(self):
        # These variables will be used for connecting and saving data to our database
        reductstore_url = "http://192.168.8.176:8383"  
        BUCKET_NAME = "temperature-data"
        current_temperature = floor(self.getFahrenheit())

        client = await Client.connect(reductstore_url)

        # Get or create the bucket
        bucket: Bucket = await client.get_or_create_bucket(BUCKET_NAME)

        while True:
            # Simulate a temperature reading
            timestamp = int(datetime.timezone.utc().timestamp() * 1e6)  # Microseconds since epoch
            data = str(current_temperature).encode("utf-8")

            # Write the data
            await bucket.write(current_temperature, data, timestamp)
            print(f"Recorded temperature: {current_temperature:.2f}°F at {datetime.timezone.utc()}")
            if(DEBUG):
                print(f"TIMESTAMPED TEMPERATURE READING SAVED TO DATABASE\n {timestamp}")
            await asyncio.sleep(10)

    ##
    ## updateLights - Utility method to update the LED indicators on the 
    ## Thermostat
    ##
    def updateLights(self):
        ## Make sure we are comparing temperatures in the correct scale
        current_temperature = floor(self.getFahrenheit())
        redLight.off()
        blueLight.off()
    
        ## Verify values for debug purposes
        if(DEBUG):
            print(f"State: {self.current_state.id}")
            print(f"SetPoint: {self.setPoint}")
            print(f"Temp: {current_temperature}")

        # Determine visual identifiers

        # If the current state is off,
        if (self.current_state.id == 'off'):
            # if the setPoint is greater 
            # than the current temperature,
            if (self.setPoint > current_temperature):
                # enter the heat state. 
                self.on_enter_heat()
                self.send("cycle_off_to_heat")
            
            # Otherwise, if the SetPoint is less 
            # than the current temperature,
            elif (self.setPoint < current_temperature):
                # enter the cool state.
                self.on_enter_cool()
                self.send("cycle_off_to_cool")

        # Otherwise (if the current state is not off),
        else:
            # if the current state is cool,
            if (self.current_state.id == 'cool'):
                # if the setPoint is greater 
                # than the current temperature,
                if (self.setPoint > current_temperature):
                    # then transition from cool
                    # state to heat state.
                    self.on_exit_cool()
                    self.on_enter_heat()
                    self.send("cycle_cool_to_heat")
            # if the current state is heat,
            if (self.current_state.id == 'heat'):
                # if the setPoint is less than 
                # the current temperature,
                if (self.setPoint < current_temperature):
                    # then transition from heat
                    # state to cool state.
                    self.on_exit_heat()
                    self.on_enter_cool()
                    self.send("cycle_heat_to_cool")

    ##
    ## run - kickoff the display management functionality of the thermostat
    ##
    def run(self):
        myThread = Thread(target=self.manageMyDisplay)
        myThread.start()

    ##
    ## Get the temperature in Fahrenheit
    ##
    def getFahrenheit(self):
        t = thSensor.temperature
        return (((9/5) * t) + 32)
    
    ##
    ##  Configure output string for the Thermostat Server
    ##
    def setupSerialOutput(self):
        ##
        ## The following output string will be sent to the 
        ## TemperatureServer over the Serial Port (UART)
        output = "State: " + str(self.current_state.id) + ", \nCurrent Temp: " + str(self.getFahrenheit()) + ", \nTarget Temp: " + str(self.setPoint)

        return output
    
    ## Continue display output
    endDisplay = False

    ##
    ##  This function is designed to manage the LCD Display
    ##
    def manageMyDisplay(self):
        counter = 1
        altCounter = 1
        while not self.endDisplay:
            ## Only display if the DEBUG flag is set
            if(DEBUG):
                print("Processing Display Info...")
    
            ## Grab the current time        
            current_time = str(datetime.now())
    
            ## Setup display line 1

            ##
            ## Setup the first line of the LCD display to incude the 
            ## current date and time.
            lcd_line_1 = datetime.now().strftime('%b %d  %H:%M:%S\n')


    
            ## Setup Display Line 2
            if(altCounter < 6):

                ##
                ## Setup the second line of the LCD display to incude the 
                # current temperature in degrees Fahrenheit. 
                temperature_string = str(round(tsm.getFahrenheit(), 2))
                line_string = ' Current: ' + temperature_string           
                
                lcd_line_2 = line_string
    
                altCounter = altCounter + 1

            else:
                state_string = str(self.current_state.id).capitalize()
                set_point_string = str(self.setPoint)
                line_string = ' ' + state_string + ' | Set: ' + set_point_string
                ##
                ## Setup the second line of the LCD display to incude the 
                ## current state of the thermostat and the current 
                ## temperature setpoint in degrees Fahrenheit. 
                lcd_line_2 = line_string
    
                altCounter = altCounter + 1
                if(altCounter >= 11):
                    # Run the routine to update the lights every 10 seconds
                    # to keep operations smooth
                    self.updateLights()
                    altCounter = 1

            ## Update Display
            temperature_screen.updateScreen(lcd_line_1 + lcd_line_2)

            ## Update server every 30 seconds
            if(DEBUG):
               print(f"Counter: {counter}")
            if((counter % 30) == 0):
                ##
                ## Send our current state information to the 
                ## TemperatureServer over the Serial Port (UART). 
                ser.write(tsm.setupSerialOutput().encode())

                counter = 1
            else:
                counter = counter + 1

            sleep(1)

        ## Cleanup display
        temperature_screen.cleanupDisplay()

    ## End class TemperatureMachine definition

#################################################################################################################
#################################################################################################################
#################################################################################################################
#####  _    _                 _     _ _ _         __  __            _     _             #########################
##### | |  | |               (_)   | (_) |       |  \/  |          | |   (_)            #########################
##### | |__| |_   _ _ __ ___  _  __| |_| |_ _   _| \  / | __ _  ___| |__  _ _ __   ___  #########################
##### |  __  | | | | '_ ` _ \| |/ _` | | __| | | | |\/| |/ _` |/ __| '_ \| | '_ \ / _ \ #########################
##### | |  | | |_| | | | | | | | (_| | | |_| |_| | |  | | (_| | (__| | | | | | | |  __/ #########################
##### |_|  |_|\__,_|_| |_| |_|_|\__,_|_|\__|\__, |_|  |_|\__,_|\___|_| |_|_|_| |_|\___| #########################
#####                                        __/ |                                      #########################
#####                                       |___/                                       #########################
#################################################################################################################
#################################################################################################################
#################################################################################################################
#################################################################################################################


class HumidityMachine(StateMachine):
    "A state machine designed to manage soil humidity"

    ##
    ## Define the three states for our machine.
    ##
    ##  off
    ##  drying
    ##  humidifying
    ##
    off = State(initial = True)
    drying = State()
    humidifying = State()

    ##
    ## Default humidity setPoint is defined here
    ##
    setPoint = 40

    ##
    ## These variables enable a safety feature which 
    ## sets a maximum and minimum target humidity level
    ##
    maxSetPoint = 100
    minSetPoint = 10


    ##
    ## cycle - event that provides the state machine behavior
    ## of transitioning between the three states of our 
    ## thermostat
    ##
    cycle = (
        off.to(drying) |
        drying.to(humidifying) |
        humidifying.to(off)
    )

    cycle_drying_to_humidifying = (
        drying.to(humidifying)
    )

    cycle_humidifying_to_drying = (
        humidifying.to(drying)
    )

    cycle_humidifying_to_off = (
        humidifying.to(off)
    )

    cycle_off_to_drying = (
        off.to(drying)
    )

    cycle_off_to_humidifying = (
        off.to(humidifying)
    )

    ##
    ## on_enter_heat - Action performed when the state machine transitions
    ## into the 'heat' state
    ##
    def on_enter_drying(self):
        ##
        ## Pulse the yellow indicator light upon entering 
        ## the 'drying' state. 
        yellowLight.pulse()

        if(DEBUG):
            print("* Changing state to drying")

    ##
    ## on_exit_heat - Action performed when the statemachine transitions
    ## out of the 'heat' state.
    ##
    def on_exit_drying(self):
        ##
        ## Turn off the yellow indicator light upon exiting 
        ## the drying state.
        yellowLight.off()

    ##
    ## on_enter_humidifying - Action performed when the state machine transitions
    ## into the 'humidifying' state
    ##
    def on_enter_humidifying(self):
        ##
        ## Pulse the green indicator light upon entering 
        ## the 'humidifying' state.
        greenLight.pulse()

        if(DEBUG):
            print("* Changing state to humidifying")

    ##
    ## on_exit_humidifying - Action performed when the statemachine transitions
    ## out of the 'humidifying' state.
    ##
    def on_exit_humidifying(self):
        ##
        ## Turn off the green indicator light upon exiting 
        ## the 'humidifying' state.
        greenLight.off()

    ##
    ## on_enter_off - Action performed when the state machine transitions
    ## into the 'off' state
    ##
    def on_enter_off(self):
        ##
        ## Turn off all lights upon entering the off state.
        yellowLight.off()
        greenLight.off()

        if(DEBUG):
            print("* Changing state to off")

   ##
    ## processHumIncButton - Utility method used to update the 
    ## setPoint for the humidity. This will increase the setPoint
    ## by a single degree. This is triggered by the button_pressed event
    ## handler for our second button
    ##
    def processHumIncButton(self):

        if(DEBUG):
            print("Increasing Set Point (Humidity)")

        ##
        ## Update the setPoint of the thermostat and the status lights
        ## within the circuit.
        # If the setPoint is less than the maximum set point, 
        if (self.setPoint < self.maxSetPoint):
            # then increment the setPoint by 1
            self.setPoint = self.setPoint + 1

    ##
    ## processHumDecButton - Utility method used to update the 
    ## setPoint for the humidity. This will decrease the setPoint
    ## by a single degree. This is triggered by the button_pressed event
    ## handler for our third button
    ##

    def processHumDecButton(self):

        if(DEBUG):
            print("Decreasing Set Point (Humidity)")

        ##
        ## Update the setPoint of the thermostat and the status lights
        ## within the circuit.
        # If the setPoint is greater than the minimum set point,
        if (self.setPoint > self.minSetPoint):
            # then decrease the set point by 1
            self.setPoint = self.setPoint - 1               

    ##
    ## updateLights - Utility method to update the LED indicators on the 
    ## Thermostat
    ##
    def updateLights(self):
        ## Make sure we are comparing humidity levels in the correct scale
        ############################################################
        ########## FIXME: Remember to change the name and ##########
        ########## logic of the getHumidity() function. ##########
        ############################################################
        hum = floor(self.getHumidity())
        ############################################################
        ############################################################
        ############################################################
        yellowLight.off()
        greenLight.off()
    
        ## Verify values for debug purposes
        if(DEBUG):
            print(f"State: {self.current_state.id}")
            print(f"SetPoint: {self.setPoint}")
            print(f"Hum: {hum}")

        # Determine visual identifiers

        # If the current state is off,
        if (self.current_state.id == 'off'):
            # if the setPoint is greater 
            # than the current humidity,
            if (self.setPoint > hum):
                # enter the drying state. 
                self.on_enter_drying()
                self.send("cycle_off_to_drying")
            
            # Otherwise, if the SetPoint is less 
            # than the current humidity,
            elif (self.setPoint < hum):
                # enter the humidifying state.
                self.on_enter_humidifying()
                self.send("cycle_off_to_humidifying")

        # Otherwise (if the current state is not off),
        else:
            # if the current state is humidifying,
            if (self.current_state.id == 'humidifying'):
                # if the setPoint is greater 
                # than the current humidity,
                if (self.setPoint > hum):
                    # then transition from humidifying
                    # state to drying state.
                    self.on_exit_humidifying()
                    self.on_enter_drying()
                    self.send("cycle_humidifying_to_drying")
            # if the current state is drying,
            if (self.current_state.id == 'drying'):
                # if the setPoint is less than 
                # the current humidity,
                if (self.setPoint < hum):
                    # then transition from drying
                    # state to humidifying state.
                    self.on_exit_drying()
                    self.on_enter_humidifying()
                    self.send("cycle_drying_to_humidifying")

    ##
    ## run - kickoff the display management functionality of the thermostat
    ##
    def run(self):
        myThread = Thread(target=self.manageMyDisplay)
        myThread.start()

    ##
    ## Get the humidity
    ##
    def getHumidity(self):
        h = thSensor.relative_humidity
        return h 
    
    ##
    ##  Configure output string for the Thermostat Server
    ##
    def setupSerialOutput(self):
        ##
        ## The following output string will be sent to the 
        ## HumidityServer over the Serial Port (UART)
        output = "State: " + str(self.current_state.id) + ", \nHumidity: " + str(self.getHumidity()) + ", \nTarget Hum: " + str(self.setPoint)

        return output
    
    ## Continue display output
    endDisplay = False

    ##
    ##  This function is designed to manage the LCD Display
    ##
    def manageMyDisplay(self):
        counter = 1
        altCounter = 1
        while not self.endDisplay:
            ## Only display if the DEBUG flag is set
            if(DEBUG):
                print("Processing Display Info...")

            

            ## Setup Display Line 2
            if(altCounter < 6):

                ##
                ## Setup display line 1
                ##
                lcd_line_1 = ' Humidity: '

                ##
                ## Setup the second line of the LCD display to incude the 
                ## current humidity. 
                ##
                humidity_string = str(round(hsm.getHumidity(), 2))         
                
                lcd_line_2 = humidity_string
    
                altCounter = altCounter + 1

            else:
                state_string = str(self.current_state.id).capitalize()
                set_point_string = str(self.setPoint)
                lcd_line_1 = ' ' + state_string + ' '
                ##
                ## Setup the second line of the LCD display to incude the 
                ## current state of the hygrometer and the current 
                ## humidity setpoint. 
                lcd_line_2 = ' Set to: ' + set_point_string
    
                altCounter = altCounter + 1
                if(altCounter >= 11):
                    # Run the routine to update the lights every 10 seconds
                    # to keep operations smooth
                    self.updateLights()
                    altCounter = 1

            ## Update Display
            humidity_screen.updateScreen(lcd_line_1 + lcd_line_2)

            ## Update server every 30 seconds
            if(DEBUG):
               print(f"Counter: {counter}")
            if((counter % 30) == 0):
                ##
                ## Send our current state information to the 
                ## HumidityServer over the Serial Port (UART). 
                ser.write(hsm.setupSerialOutput().encode())

                counter = 1
            else:
                counter = counter + 1

            sleep(1)

        ## Cleanup display
        humidity_screen.cleanupDisplay()

    ## End class HumidityMachine definition

##
## Create a TemperatureStateMachine object called tsm
##
tsm = TemperatureMachine()

##
## This function sets up and starts a state machine of type TemperatureStateMachine
##
def runTemperatureStateMachine():
    ##
    ## Setup our Temperature State Machine
    ##
    
    tsm.run()

    ##
    ## Configure our Red button to use GPIO 25 and to execute
    ## the function to increase the setpoint by a degree.
    ##
    tempIncButton = Button(25)

    ##
    ## Change the value of the temperature setpoint when 
    ## the red button is pushed.
    tempIncButton.when_pressed = tsm.processTempIncButton

    ##
    ## Configure our Blue button to use GPIO 12 and to execute
    ## the function to decrease the setpoint by a degree.
    ##
    tempDecButton = Button(12)
    ##
    ## Change the value of the temperature setpoint when 
    ## the blue button is pushed.
    tempDecButton.when_pressed = tsm.processTempDecButton

    ##
    ## Setup loop variable
    ##
    repeat = True

    ##
    ## Repeat until the user creates a keyboard interrupt (CTRL-C)
    ##
    while repeat:
        try:
            asyncio.run(tsm.updateDB())
            ## wait
            sleep(30)

        except KeyboardInterrupt:
            ## Catch the keyboard interrupt (CTRL-C) and exit cleanly
            ## we do not need to manually clean up the GPIO pins, the 
            ## gpiozero library handles that process.
            print("Cleaning up. Exiting...")

            ## Stop the loop
            repeat = False
            
            ## Close down the display
            tsm.endDisplay = True
            sleep(1)

##
## Create a HumidityStateMachine object called hsm
##
hsm = HumidityMachine()

##
## This function sets up and starts a state machine of type HUmidityStateMachine
##
def runHumidityStateMachine():
    ##
    ## Setup our Humidity State Machine
    ##
    hsm.run()

    ##
    ## Configure our humIncButton (humidity increase button) 
    #  to use GPIO pin 24.
    ##
    humIncButton = Button(24)
    ##
    ## Change the state of our thermostat when 
    ## the green button is pushed.
    humIncButton.when_pressed = hsm.processHumIncButton

    ##
    ##
    ## Configure our humDecButton (humidity decrease button) 
    #  to use GPIO pin 16.
    ##
    humDecButton = Button(16)
    ##
    ## Change the state of our thermostat when 
    ## the green button is pushed.
    humDecButton.when_pressed = hsm.processHumDecButton
    ##
    ## Setup loop variable
    ##
    repeat = True

    ##
    ## Repeat until the user creates a keyboard interrupt (CTRL-C)
    ##
    while repeat:
        try:
            ## wait
            sleep(30)

        except KeyboardInterrupt:
            ## Catch the keyboard interrupt (CTRL-C) and exit cleanly
            ## we do not need to manually clean up the GPIO pins, the 
            ## gpiozero library handles that process.
            print("Cleaning up. Exiting...")

            ## Stop the loop
            repeat = False
            
            ## Close down the display
            hsm.endDisplay = True
            sleep(1)

##
## This is our main function which runs an instance of each state machine
## in a separate thread.
##
def main():

    tracemalloc.start()

    ## Create a thread for the HumidityStateMachine
    temperature_control_thread = threading.Thread(target=runTemperatureStateMachine,)

    ## Create a thread for the TemperatureStateMachine
    humidity_control_thread = threading.Thread(target=runHumidityStateMachine,)

    ## Start the tempratureControlThread
    temperature_control_thread.start()

    ## Start the humidityControlThread
    humidity_control_thread.start()

## Call our main function.
main()
