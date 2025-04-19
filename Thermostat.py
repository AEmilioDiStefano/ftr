#
# Thermostat - This is the Python code used to demonstrate
# the functionality of the thermostat that we have prototyped throughout
# the course. 
#
# This code works with the test circuit that was built for module 7.
#
# Functionality:
#
# The thermostat has three states: off, heat, cool
#
# The lights will represent the state that the thermostat is in.
#
# If the thermostat is set to off, the lights will both be off.
#
# If the thermostat is set to heat, the Red LED will be fading in 
# and out if the current temperature is blow the set temperature;
# otherwise, the Red LED will be on solid.
#
# If the thermostat is set to cool, the Blue LED will be fading in 
# and out if the current temperature is above the set temperature;
# otherwise, the Blue LED will be on solid.
#
# One button will cycle through the three states of the thermostat.
#
# One button will raise the setpoint by a degree.
#
# One button will lower the setpoint by a degree.
#
# The LCD display will display the date and time on one line and
# alternate the second line between the current temperature and 
# the state of the thermostat along with its set temperature.
#
# The Thermostat will send a status update to the TemperatureServer
# over the serial port every 30 seconds in a comma delimited string
# including the state of the thermostat, the current temperature
# in degrees Fahrenheit, and the setpoint of the thermostat.
#
#------------------------------------------------------------------
# Change History
#------------------------------------------------------------------
# Version   |   Description
#------------------------------------------------------------------
#    1          Initial Development
#------------------------------------------------------------------

##
## Import necessary to provide timing in the main loop
##
from time import sleep
from datetime import datetime

##
## Imports required to allow us to build a fully functional state machine
##
from statemachine import StateMachine, State

##
## Imports necessary to provide connectivity to the 
## thermostat sensor and the I2C bus
##
import board
import adafruit_ahtx0
import adafruit_sht31d

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
## Our two LEDs, utilizing GPIO 18, and GPIO 23
##
redLight = PWMLED(18)
blueLight = PWMLED(23)

##
## ManagedDisplay - Class intended to manage the 16x2 
## Display
##
## This code is largely taken from the work done in module 4, and
## converted into a class so that we can more easily consume the 
## operational capabilities.
##
class ManagedDisplay():
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
        self.lcd_en = digitalio.DigitalInOut(board.D27)
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
## Initialize our display
##
screen = ManagedDisplay()

##
## TemperatureMachine - This is our StateMachine implementation class.
## The purpose of this state machine is to manage the three states
## handled by our thermostat:
##
##  off
##  heat
##  cool
##
##
class TemperatureMachine(StateMachine):
    "A state machine designed to manage our thermostat"

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

        if(DEBUG):
            print("* Exiting cool state")

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

        if(DEBUG):
            print("* Exiting cool state")

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
    ## processTempStateButton - Utility method used to send events to the 
    ## state machine. This is triggered by the button_pressed event
    ## handler for our first button
    ##
    def processTempStateButton(self):
        if(DEBUG):
            print("Cycling Temperature State")

        ##
        ## Change the state of the thermostat.        
        self.send("cycle")

    ##
    ## processTempIncButton - Utility method used to update the 
    ## setPoint for the temperature. This will increase the setPoint
    ## by a single degree. This is triggered by the button_pressed event
    ## handler for our second button
    ##
#########################################################################################

    def processTempIncButton(self):

        if(DEBUG):
            print("Increasing Set Point")

        ##
        ## Update the setPoint of the thermostat and the status lights
        ## within the circuit.
        # If the setPoint is less than the maximum set point, 
        if (self.setPoint < self.maxSetPoint):
            # then increment the setPoint by 1
            self.setPoint = self.setPoint + 1

            if (self.current_state.id == 'heat'):
                redLight.on()

#########################################################################################



    ##
    ## processTempDecButton - Utility method used to update the 
    ## setPoint for the temperature. This will decrease the setPoint
    ## by a single degree. This is triggered by the button_pressed event
    ## handler for our third button
    ##
#########################################################################################

    def processTempDecButton(self):

        if(DEBUG):
            print("Decreasing Set Point")

        ##
        ## Update the setPoint of the thermostat and the status lights
        ## within the circuit.
        # If the setPoint is greater than the minimum set point,
        if (self.setPoint > self.minSetPoint):
            # then decrease the set point by 1
            self.setPoint = self.setPoint - 1

        if (self.current_state.id == 'cool'):
            blueLight.on()

#########################################################################################

    ##
    ## updateLights - Utility method to update the LED indicators on the 
    ## Thermostat
    ##
    def updateLights(self):
        ## Make sure we are comparing temperatures in the correct scale
        temp = floor(self.getFahrenheit())
        redLight.off()
        blueLight.off()
    
        ## Verify values for debug purposes
        if(DEBUG):
            print(f"State: {self.current_state.id}")
            print(f"SetPoint: {self.setPoint}")
            print(f"Temp: {temp}")

        # Determine visual identifiers

########## TODO ########## TODO ########## TODO ########## TODO ##########
## TODO ########## TODO ########## TODO ########## TODO ########## TODO ##
########## TODO ########## TODO ########## TODO ########## TODO ##########
#      | |
#      | |
#   |\ | | /|
#   \ \| |/ /
#    \     /
#     \   /
#      \ /

        # If the current state is off,
        if (self.current_state.id == 'off'):
            # if the setPoint is greater 
            # than the current temperature,
            if (self.setPoint > temp):
                # enter the heat state.
                self.on_enter_heat()
                self.send("cycle")
            
            # Otherwise, if the SetPoint is less 
            # than the current temperature,
            elif (self.setPoint < temp):
                # enter the cool state.
                self.on_enter_cool()
                self.send("cycle")

        # Otherwise (if the current state is not off),
        else:
            # if the current state is cool,
            if (self.current_state.id == 'cool'):
                # if the setPoint is greater 
                # than the current temperature,
                if (self.setPoint > temp):
                    # then transition from cool
                    # state to heat state.
                    self.on_exit_cool()
                    self.on_enter_heat()
                    self.send("cycle_cool_to_heat")
            # if the current state is heat,
            if (self.current_state.id == 'heat'):
                # if the setPoint is less than 
                # the current temperature,
                if (self.setPoint < temp):
                    # then transition from heat
                    # state to cool state.
                    self.on_exit_heat()
                    self.on_enter_cool()
                    self.send("cycle_heat_to_cool")

#       / \
#      /   \
#     /     \
#    / /| |\ \
#    |/ | | \|
#       | |
#       | |
########## TODO ########## TODO ########## TODO ########## TODO ##########
## TODO ########## TODO ########## TODO ########## TODO ########## TODO ##
########## TODO ########## TODO ########## TODO ########## TODO ##########

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
            current_time = datetime.now()
    
            ## Setup display line 1

            ##
            ## Setup the first line of the LCD display to incude the 
            ## current date and time.
            lcd_line_1 = current_time

########## TODO ########## TODO ########## TODO ########## TODO ##########
## TODO ########## TODO ########## TODO ########## TODO ########## TODO ##
########## TODO ########## TODO ########## TODO ########## TODO ##########
#      | |
#      | |
#   |\ | | /|
#   \ \| |/ /
#    \     /
#     \   /
#      \ /
    
            ## Setup Display Line 2
            if(altCounter < 6):
                ##
                ## Setup the second line of the LCD display to incude the 
                # current temperature in degrees Fahrenheit. 
                temp_string = str(round(tsm.getFahrenheit(), 2))
                lcd_line_2 = str(f"Current temp: {temp_string}")
    
                altCounter = altCounter + 1
            else:
                ##
                ## Setup the second line of the LCD display to incude the 
                ## current state of the thermostat and the current 
                ## temperature setpoint in degrees Fahrenheit. 
                lcd_line_2 = str(f"{self.current_state.id} Setpoint: {self.setPoint}")
    
                altCounter = altCounter + 1
                if(altCounter >= 11):
                    # Run the routine to update the lights every 10 seconds
                    # to keep operations smooth
                    self.updateLights()
                    altCounter = 1

            ## Update Display
            screen.updateScreen(str(lcd_line_1) + str(lcd_line_2))


#       / \
#      /   \
#     /     \
#    / /| |\ \
#    |/ | | \|
#       | |
#       | |
########## TODO ########## TODO ########## TODO ########## TODO ##########
## TODO ########## TODO ########## TODO ########## TODO ########## TODO ##
########## TODO ########## TODO ########## TODO ########## TODO ##########

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
        screen.cleanupDisplay()

    ## End class TemperatureMachine definition


##
## Setup our State Machine
##
tsm = TemperatureMachine()
tsm.run()

##
## Configure our green button to use GPIO 24 and to execute
## the method to cycle the thermostat when pressed.
##
greenButton = Button(24)
##
## Change the state of our thermostat when 
## the green button is pushed.
greenButton.when_pressed = tsm.processTempStateButton

##
## Configure our Red button to use GPIO 25 and to execute
## the function to increase the setpoint by a degree.
##
redButton = Button(25)
##
## Change the state of our thermostat when 
## the red button is pushed.
redButton.when_pressed = tsm.processTempIncButton

##
## Configure our Blue button to use GPIO 12 and to execute
## the function to decrease the setpoint by a degree.
##
blueButton = Button(12)
##
## Change the state of our thermostat when 
## the blue button is pushed.
blueButton.when_pressed = tsm.processTempDecButton

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
        tsm.endDisplay = True
        sleep(1)
