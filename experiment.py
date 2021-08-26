# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

import random
import klibs
from klibs import P
from klibs.KLGraphics import *
from klibs.KLUtilities import *
#from klibs.KLUserInterface import *
from klibs.KLConstants import *
from klibs.KLKeyMap import KeyMap
from klibs.KLResponseCollectors import KeyPressResponse as KPR
from klibs.KLGraphics.KLNumpySurface import *
from CompTrack import *
import klibs.KLDatabase
import subprocess


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

		# Set session parameters
		self.comp_track.session_params['exp_duration'] = 300  # Total duration of session, in seconds
		self.comp_track.session_params['reset_target_after_poll'] = True  # Should cursor reset to center after PVT events?


		# Ensure mouse starts at centre and set invisible
		mouse_pos(False, P.screen_c)
		hide_mouse_cursor()


	def block(self):
		pass

	def setup_response_collector(self):
		self.rc.uses(KPR('pvt_response_listener'))
		self.rc.pvt_response_listner.key_map = KeyMap('space', 'SPACE', ' ')
		self.rc.pvt_response_listner.interrupts = True
		self.rc.display_callback = self.comp_track.refresh
		self.rc.before_return_callback = self.event_label
		self.rc.before_return_args = ['response', self.evm.trial_time]

	def trial_prep(self):
		self.evm.register_ticket(self.ev_label, self.comp_track.next_trial_start_time)
		self.comp_track.next_trial_start_time = self.evm.trial_time + self.itis.pop()
		while self.evm.before(self.ev_label):
			self.ui_request(True)

	def trial(self):
		self.ComptTrack.end_trial(self.rc.collect()[1])

		trial_data = {
			"block_num": P.block_number,
			"trial_num": P.trial_number,
			'participant_id': P.participant_id,
		}
		frame_keys = ['timestamp', 'buffeting_force', 'additional_force', 'net_force', 'user_input', 'target_position', 'displacement', 'rt']
		frame_data = {frame_keys[i]: self.CompTrack.current_frame.dump()[i] for i in range(len(frame_keys))}
		trial_data.update(frame_data)

		return trial_data

	def trial_clean_up(self):
		pass

	def clean_up(self):
		for a in self.comp_track.assessments:
			self.db.insert(a.dump(), 'assessments')

		for f in self.comp_track.frames:
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
		if (0.25 * P.trial_count * P.pvt_timeout) + (P.trial_count * sum(P.iti) * 0.5) < P.exp_duration:
			raise ValueError("It is unlikely this number of trials can be completed in the allotted time.")

		# start with a uniform block of minimum itis
		self.itis = P.trials_per_block * P.blocks_per_experiment * [P.iti[0]]

		surplus = P.experiment_duration - sum(self.itis)
		if surplus > P.trials_per_block * P.blocks_per_experiment * [P.iti[1]]:
			raise ValueError("This experiment duration cannot be met with this trial count/ITI combination.")
		while surplus > 0:
			index = random.randint(0,len(self.itis))
			if self.itis[index] < P.iti[1]:
				self.itis[index] += 1
				surplus -= 1







	def response_callback(self):
		self.rc.pvt_keyboard_response.responses[-1].append(self.frame_id())

	def event_label(self, event):
			return "trial_{}_{}".format(P.trial_number, event)

	def current_frame_id(self):
		return "{}:{}".format(P.trial_number - 1, len(self.frames[P.trial_number] - 1)
)