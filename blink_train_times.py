#!/usr/bin/python
# -*- coding: utf8 -*-

'''
title           : 	blink_train_times.py
description     : 	Poll trafiklab.se real-time traffic information and display train 
							departure times using a blink(1) device
							Let t be time until next train departure in minutes, then:
							15 < t:	 		red
							12 < t < 15:	green
							10 < t < 12:	yellow
							8 < t < 10:		blink yellow
							0 < t < 8:		red
author          : 	Marcus Mikulcak
'''

import time, sys
import urllib
from xml.dom.minidom import parse
import threading
import argparse

import signal
from datetime import datetime

try:
	import usb
except ImportError:
	print "PyUSB is needed"
	sys.exit()

class blink_thread(threading.Thread):
	
	current_color = [0, 0, 0]

	cancel = False
	currently_blinking = False

	blink_device = None
	
	def __init__(self, color=[255,255,255]):
		self.cancel = False
		self.currently_blinking = False
		self.current_color = color

		# find the blink(1) device
		self.blink_device = usb.core.find(idVendor=0x27b8, idProduct=0x01ed)
		assert self.blink_device is not None, "No blink(1) device found..."

		threading.Thread.__init__(self)

	def stop_thread(self):
		self.cancel = True

	def set_new_color(self, new_color):
		self.current_color = new_color

	def blink(self):
		self.currently_blinking = True

	def stop_blinking(self):
		self.currently_blinking = False

	def run(self):
		# fade to self.current_color every second
		# and stop when the thread has been asked to do so

		# create the usb request (based on code in https://github.com/todbot/blink1/blob/master/python/blink1hid-demo.py)
		bmRequestTypeOut = usb.util.build_request_type(usb.util.CTRL_OUT, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_INTERFACE)
		# fade to color with timing set below: 0x63 
		action = 0x63

		while True and not self.cancel:
			if self.currently_blinking == False:
				# if blinking is currently turned off, simply fade to color
				# build the USB command content
				red = self.current_color[0]
				green = self.current_color[1]
				blue = self.current_color[2]
				# a device timing tick is 10ms long, so 50 ticks will lead to a 500ms fade
				ticks = 90
				th = (ticks & 0xff00) >> 8
				tl = ticks & 0x00ff
				self.blink_device.ctrl_transfer(bmRequestTypeOut, 0x09, (3 << 8) | 0x01, 0, [0x00, action, red, green, blue, th, tl, 0x00, 0x00])
				# check for new color and send new command in one second
				time.sleep(1)
			else:
				# if blinking is currently turned on, things go crazy
				# build the USB command content
				# first fade to black (off)
				ticks = 40
				th = (ticks & 0xff00) >> 8
				tl = ticks & 0x00ff
				red = 0
				green = 0
				blue = 0
				self.blink_device.ctrl_transfer(bmRequestTypeOut, 0x09, (3 << 8) | 0x01, 0, [0x00, action, red, green, blue, th, tl, 0x00, 0x00])
				time.sleep(0.5)
				# now fade back to the currently set color
				red = self.current_color[0]
				green = self.current_color[1]
				blue = self.current_color[2]
				self.blink_device.ctrl_transfer(bmRequestTypeOut, 0x09, (3 << 8) | 0x01, 0, [0x00, action, red, green, blue, th, tl, 0x00, 0x00])
				time.sleep(0.50)


class blink_controller():

	spawned_blink_thread = None

	def set_new_color(self, new_color):
		self.spawned_blink_thread.set_new_color(new_color)

	def start_blinking(self):
		self.spawned_blink_thread.blink()

	def stop_blinking(self):
		self.spawned_blink_thread.stop_blinking()

	def __init__(self, new_color):
		self.spawned_blink_thread = blink_thread()

	def spawn_blink_thread(self):
		self.spawned_blink_thread.start()

	def goodbye(self):
		self.spawned_blink_thread.stop_thread()


# this returns the list of departure time strings
def find_correct_departure(dom):

	# find all departures of line 36 to Märsta
	list_of_departures_times = []

	for train in dom.getElementsByTagName('Trains'):
		for train_departure in train.getElementsByTagName('DpsTrain'):
			# check if the current departure element is going into the right direction ("2" going north)
			if train_departure.getElementsByTagName('JourneyDirection').item(0).firstChild.data != "2":
				# if the direction of this departure is wrong, continue to next departure element
				continue
			else:
				# for the correct direction, check if the line number is correct ("36" going to Märsta)
				if train_departure.getElementsByTagName('LineNumber').item(0).firstChild.data == "36":
					# add the departure time of this matching departure element to the list to be returned
					list_of_departures_times.append(train_departure.getElementsByTagName('ExpectedDateTime').item(0).firstChild.data)

	return list_of_departures_times


# this calls the find_correct_departure() method and compares the list of results with the current time
# if the results are too close together, e.g. if there are to trains with the next twelve minutes,
# return the time difference to the later one
def find_next_departure(dom):
	departure = find_correct_departure(dom)

	seconds_to_departure_list = []
	for departure_time_string_entry in departure:
		next_departure = time.strptime(departure_time_string_entry, "%Y-%m-%dT%H:%M:%S")
		dt = datetime.fromtimestamp(time.mktime(next_departure))
		time_now = datetime.now()
		time_difference = dt - time_now
		seconds_to_departure_list.append(time_difference.seconds)

	closest_departure = 0

	if len(seconds_to_departure_list) > 1:
		# if the second departure is earlier than in twelve minutes, skip the next one
		if (seconds_to_departure_list[1] - seconds_to_departure_list[0]) < 720:
			closest_departure = seconds_to_departure_list[1]
		else:
			closest_departure = seconds_to_departure_list[0]
	else:
		closest_departure = seconds_to_departure_list[0]

	return closest_departure



# this calls find_next_departure() and sets the color according to its return value
def get_information_and_update_blink(blink_instance, dom):
	time_difference = find_next_departure(dom)

	# turn off device blinking
	blink_instance.stop_blinking()

	print str(time_difference) + " seconds until the next train leaves to the city, set to",
	if time_difference > 900:
		# the next train comes in more than 15 minutes, turn to red
		print "red..."
		blink_instance.set_new_color([255, 0, 0])
	elif time_difference > 720:
		# train comes in more than 12 minutes, turn to green
		print "green..."
		blink_instance.set_new_color([0, 255, 0])
	elif time_difference > 600:
		# train comes in less than 12 but more than 10 minutes, turn to yellow
		print "yellow..."
		blink_instance.set_new_color([255, 255, 0])
	elif time_difference > 480:
		# train comes in less than 10 but more than 8 minutes, turn to yellow and start blinking
		print "yellow and blink..."
		blink_instance.start_blinking()
		blink_instance.set_new_color([255, 255, 0])
	else:
		# the next train leaves in less than 8 minutes, turn to red
		print "red..."
		blink_instance.set_new_color([255, 0, 0])

# has to be global to be visible to the signal handler function
train_blink_controller = blink_controller([255, 0,0])

def handler(signum, frame):
	print "\nGoodbye"
	train_blink_controller.goodbye()
	sys.exit()

def get_traffic_information(schedule_url):
	try:
		current_information = urllib.urlopen(schedule_url)
		return current_information
	except IOError:
		print "An error occured while trying to fetch the new traffic information data, using old data..."
		return None


def main():
	parser = argparse.ArgumentParser(description='Receive train departure information from trafiklab.se and show them via a blink(1) device.')
	parser.add_argument('--api_key', 
								action='store', 
								default="", 
								help='The API key from trafiklab.se',
								required=True)

	parser.add_argument('--station_id', 
								action='store', 
								default="9526", # Flemingsberg, commuter trains
								help='The station ID to be checked',
								required=False)

	args = parser.parse_args()

	print "Using API key " + args.api_key

	train_blink_controller.spawn_blink_thread()

	schedule_url = "https://api.trafiklab.se/sl/realtid/GetDpsDepartures?key=" + str(args.api_key) + "&siteid=" + str(args.station_id)

	current_information = None
	saved_information = None

	signal.signal(signal.SIGINT, handler)

	while True:
		current_information = get_traffic_information(schedule_url)
		if current_information != None:
			try:
				dom = parse(current_information)
			except:
				print "An error occured parsing the information, trying again in ten seconds..."
				time.sleep(10)
				continue
			saved_information = current_information
		else:
			if saved_information == None:
				print "An error occured while trying to get the traffic information and no stored information was found, trying again in ten seconds..."
				time.sleep(10)
				continue
		get_information_and_update_blink(train_blink_controller, dom)
		time.sleep(10)

if __name__ == "__main__":
    main()
