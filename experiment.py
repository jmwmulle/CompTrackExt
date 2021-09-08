# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"
from sdl2 import SDL_GetKeyFromName, SDL_KEYDOWN, SDL_KEYUP, SDL_MOUSEBUTTONDOWN, SDL_MOUSEBUTTONUP, SDLK_SPACE
import random
import klibs
from klibs import P
from klibs.KLUserInterface import ui_request
from klibs.KLResponseCollectors import KeyPressResponse, KeyMap
from klibs.KLGraphics import *
from klibs.KLUtilities import *
from klibs.KLEventInterface import TrialEventTicket as TVT
from klibs.KLConstants import *
from klibs.KLKeyMap import KeyMap
from klibs.KLResponseCollectors import Response, KeyPressResponse
import sdl2
from klibs.KLGraphics.KLNumpySurface import *
from CompTrack import *
import klibs.KLDatabase
import subprocess

from klibs.KLDatabase import EntryTemplate

class CompensatoryTrackingTask(klibs.Experiment):


	def setup(self):
		# Ensure display has been wiped before starting
		clear()
		flip()


		self.frames = []  # data for every screen refresh are captured and stored by trial

		# Ensure mouse-shake setting is disabled, as it will be triggered by mouse input
		if not P.development_mode:
			self.txtm.add_style('UserAlert', 16, (255, 000, 000))
			self.check_osx_mouse_shake_setting()

		# CompTrack class handles all events
		self.comp_track = CompTrack()
		self.comp_track.timeout_after = P.pvt_timeout
		self.generate_ITIs()


		# Ensure mouse starts at centre and set invisible
		mouse_pos(False, P.screen_c)
		hide_mouse_cursor()


	def block(self):
		pass

	def setup_response_collector(self):
		pass

	def trial_prep(self):
		self.comp_track.next_trial_start_time = now() + self.itis.pop()
		self.start = now()
		pump()

	def trial(self):
		start = now()
		rt = -1

		while now() < self.comp_track.next_trial_start_time + P.pvt_timeout:
			event_q = pump(True)
			ui_request(None, True, event_q)
			self.comp_track.refresh(event_q)
			if now() >= self.comp_track.next_trial_start_time:
				for event in event_q:
					if event.type == SDL_KEYDOWN and event.key.keysym == SDLK_SPACE:
						key = event.key.keysym # keyboard button event object
						ui_request(key) # check for ui requests (ie. quit, calibrate)
						if key == SDLK_SPACE:
							rt = now() - start
							break
		if not rt:
			# here's where we could  add feedback immediately after a lapse, were it desired
			pass
		self.comp_track.end_trial(rt)

		return {'block_num': P.block_number,
				'trial_num' : P.trial_number,
				'timestamp': self.comp_track.current_frame.timestamp,
				'rt': self.comp_track.current_frame.rt
		}

	def trial_clean_up(self):
		pass

	def clean_up(self):
		for a in self.comp_track.assessments:
			self.db.insert(a.dump(), 'assessments')

		for trial in self.comp_track.frames:
			for f in trial:
				self.db.insert(f.dump(), 'frames')


	def check_osx_mouse_shake_setting(self):
		p = subprocess.Popen(
		"defaults read ~/Library/Preferences/.GlobalPreferences CGDisableCursorLocationMagnification 1", shell=True)

		if p is 0:
			fill((25, 25, 28))
			blit(NumpySurface(import_image_file('ExpAssets/Resources/image/accessibility_warning.png')), 5, P.screen_c)
			msg = 'Please ensure cursor shake-magnification is off before running this experiment.'
			x_pos = int((P.screen_y - 568) * 0.25) + 16
			message(msg, 'UserAlert', [P.screen_c[0], x_pos], 5)
			flip()
			any_key()
			quit()

	def generate_ITIs(self):

		trial_count = P.trials_per_block * P.blocks_per_experiment
		expected_duration = (0.5 * trial_count * P.pvt_timeout) + ( trial_count * sum(P.iti) * 0.5)

		if expected_duration > P.experiment_duration:
			raise ValueError("It is unlikely this number of trials, of the proposed ITIs, can be completed in the allotted time.")

		# start with a uniform block of minimum itis
		self.itis = P.trials_per_block * P.blocks_per_experiment * [P.iti[0]]

		surplus = P.experiment_duration - sum(self.itis)

		if surplus > P.trials_per_block * P.blocks_per_experiment * [P.iti[1]]:
			raise ValueError("This experiment duration cannot be met with this trial count/ITI combination.")
		while surplus > 0:
			index = random.randint(0,len(self.itis) -1)
			if self.itis[index] < P.iti[1]:
				self.itis[index] += 1
				surplus -= 1
			surplus = P.experiment_duration - sum(self.itis)

	@property
	def event_queue(self):
		return pump(True)

	def response_callback(self):
		self.rc.pvt_keyboard_response.responses[-1].append(self.frame_id())

	def event_label(self, event):
			return "trial_{}_{}".format(P.trial_number, event)

	def current_frame_id(self):
		return "{}:{}".format(P.trial_number - 1, len(self.frames[P.trial_number] - 1)



)



class PVTResponse(KeyPressResponse):
	__name__ = 'pvt_listener'

	def init(self):
		pass
		# self.__name__ = "pvt_listener"

	def listen(self, event_queue):
		for event in event_queue:
			if event.type == SDL_KEYDOWN:
				key = event.key.keysym # keyboard button event object
				ui_request(key) # check for ui requests (ie. quit, calibrate)
				if key == SDLK_SPACE:
					return Response(True, self.evm.trial_time_ms - self._rc_start)
				# if self.key_map.validate(key.sym):
				# 	value = self.key_map.read(key.sym, "data")
				# 	rt = (self.evm.trial_time_ms - self._rc_start)
				# 	return Response(value, rt)