# CompTrack.py
# Brett Feltmate, 2021
# A reformulation of http://github.com/jmwmulle/PVTarget

# Presents a cursor/target which is horizontally buffeted by
# an undulating sinusoidal function. User, via mouse input,
# is tasked to maintain cursor position at screen center.

# At psuedo-random points a PVT counter is presented centre-screen
# to which to user must halt via pressing spacebar.

# Class functionality will eventually be expanded to allow for:
#  - dynamically setting difficulty conditional on PVT performance
#  - presenting alerting signals either randomly or conditionally

from copy import deepcopy
import abc

import os
import numpy as np
import sdl2
from klibs.KLCommunication import *
from klibs.KLConstants import *
from klibs.KLEnvironment import EnvAgent
from klibs.KLGraphics.KLDraw import *
from klibs.KLUtilities import *
from klibs.KLAudio import AudioClip
sdl2.SDL_SetRelativeMouseMode(sdl2.SDL_TRUE)



class CompTrack(EnvAgent):
	def __init__(self):
		super(CompTrack, self).__init__()
		self.__init_time = now()

		self.frames = []
		self.assessments = []
		self._position = None

		#
		# Define styles & create stimuli
		#
		self.palette = {
			'grue': (25, 25, 28), # mysteriously, leading zero throws a syntax error in last value
			'white': (255, 255, 255),
			'red': (255, 000, 000),
			'green': (000, 255, 000),
			'black': (000, 000, 000)
		}

		self.stim_sizes = {
			'cursor': deg_to_px(1),
			'fixation': [deg_to_px(1.4), deg_to_px(0.2)],
			'PVT_frame': [deg_to_px(6), deg_to_px(3)],
			'PVT_digits': deg_to_px(1.5),
			'inner_ring': [P.screen_x * 0.3, deg_to_px(0.1)],
			'middle_ring': [P.screen_x * 0.6, deg_to_px(0.1)],
			'outer_ring': [P.screen_x * 0.9, deg_to_px(0.1)]
		}

		# PVT digit text style
		self.txtm.add_style('PVT_digits', self.stim_sizes['PVT_digits'] * .75, self.palette['white'])

		# Visual assets
		self.assets = {
			'fixation': Annulus(
				diameter=self.stim_sizes['fixation'][0],
				thickness=self.stim_sizes['fixation'][1],
				fill=self.palette['white']
			),
			'inner_ring': Annulus(
				diameter=self.stim_sizes['inner_ring'][0],
				thickness=self.stim_sizes['inner_ring'][1],
				fill=self.palette['red']
			),
			'middle_ring': Annulus(
				diameter=self.stim_sizes['middle_ring'][0],
				thickness=self.stim_sizes['middle_ring'][1],
				fill=self.palette['red']
			),
			'outer_ring': Annulus(
				diameter=self.stim_sizes['outer_ring'][0],
				thickness=self.stim_sizes['outer_ring'][1],
				fill=self.palette['red']
			),
			'cursor': Circle(
				diameter=self.stim_sizes['cursor'],
				fill=self.palette['green']
			),
			'PVT_frame': Rectangle(
				width=self.stim_sizes['PVT_frame'][0],
				height=self.stim_sizes['PVT_frame'][1],
				stroke=[2, self.palette['red'], STROKE_OUTER]
			).render()
		}

		# Prepared DB statements
		self.lapse_query_str = "SELECT COUNT(*) FROM `trials` WHERE `participant_id` = {0} AND `rt` = false AND `trial_num` > {1}"
		self.mean_rt_query_str = "SELECT SUM(*) FROM `trials` WHERE `participant_id` = {0} AND `rt` != false AND `trial_num` > {1} / {2}"

		# PVT config
		self.max_input_step = P.max_input_step
		self.supervise_input = P.supervise_input
		self.forces = {'buffeting': None, 'additional': None, 'net': None}
		self.timeout_after = None
		self.poll_while_moving = P.poll_while_moving
		self.poll_at_fixation = P.poll_at_fixation
		self.reset_target_after_poll = P.reset_target_after_poll
		self.x_bounds = [int(0.5 * self.stim_sizes['cursor']),int(P.screen_x - 0.5 * self.stim_sizes['cursor'])]

		# performance assessments
		self.assessment_sample_size = P.assessment_sample_size
		self.assessing = P.assessing
		self.max_mean_rt = P.max_mean_rt
		self.excessive_lapse_threshold = P.excessive_lapse_threshold
		self.__next_trial_start_time = None

		# mitigations
		self.audio_warning_file_path = P.audio_warning_file_path
		self.audio_warning_duration = P.audio_warning_duration
		self.pause_duration = None
		self.pausing_clears_screen = P.pausing_clears_screen
		self.pause_targets = P.pause_targets
		self.mitigating = False  # only true when a mitigation has run
		self.current_mitigation = None

		# set an initial mouse position
		self.position = P.screen_c[0]

	def assess_performance(self):
		"""
		Used to access currently recorded data by variable column
		"""
		try:
			assessment = CompTrackAssessment()
			query_data = [P.participant_id, P.trial_number - (1 + self.assessment_sample_size)]

			assessment.lapse_count = self.db.query(self.lapse_query_str.format(*query_data), fetch_all=True)[0][0]
			assessment.mean_rt = self.db.query(self.mean_rt_query_str.format(*query_data), fetch_all=True)[0]
			self.assessments.append(assessment)

			if self.assessing['lapses'] and assessment.lapse_count >= self.excessive_lapse_threshold:
				self.excessive_lapse_callback()

			if self.assessing['mean_rt'] and assessment.mean_rt >= self.max_mean_rt:
				self.excessive_mean_rt_callback()

		except IndexError:
			pass

	def end_trial(self, rt):
		self.current_frame.rt= rt
		self.assess_performance()		# does nothing if keys in P.assessing are False
		if self.reset_target_after_poll:
		 	self.position = P.screen_c[0]
		self.next_trial_start_time = None

	def refresh(self, event_queue):
		# update any mitigations currently in execution
		try:
			self.current_mitigation.update()
		except AttributeError:
			pass  # i.e. None

		# start a new frame object to capture all the activity of this refresh
		self.__new_frame()

		# Compute buffeting forces
		self.__compute_forces()

		# then iteratively add all force contributions to current position, if they exist on this pass
		for force in ['net', 'additional', 'buffeting']:
			try:
				self.position = self.position  + self.current_frame.forces[force]
			except TypeError:
				pass

		# needed for subsequent statements
		self.__capture_mouse_input(event_queue)

		# set initial position update based on mouse activity
		self.position = self.position + self.current_frame.user_input

		self.__render()
		self.current_frame.displacement = line_segment_len(P.screen_c, [self.position, P.screen_c[1]])
		self.current_frame.target_position = self.position



	def mitigate(self, m_type):
		if m_type is "Audio":
			self.current_mitigation = AudioMitigation(self, self.audio_warning_file_path, self.audio_warning_duration)
			self.current_mitigation.run()

		if m_type is "pause":
			self.current_mitigation = PauseMitigation(self, self.pause_duration, self.pausing_clears_screen, self.pause_targets)
			self.current_mitigation.run()

	def excessive_lapse_callback(self):
		pass


	def excessive_mean_rt_callback(self):
		pass

	def __clear_mitigations(self):
		"""
		This just exists because the mitigation objects can't unset themselves, and only mitigation objects call it.
		"""
		self.mitigating = False
		self.current_mitigation = None

	def __new_frame(self):
		try:
			self.frames[P.trial_number - 1].append(CompTrackFrame(self.exp.current_frame_id, now()))
		except IndexError:
			self.frames.append([])
			self.__new_frame()
		self.current_frame.target_position = self.position

	def __render(self):
		"""
		Renders stimuli to screen.
		"""
		debug_this = False
		if debug_this: print "\n\n>>> __render() >>>"

		# if pausing everything, just don't ever blit or flip, EZ
		if self.mitigating and self.current_mitigation.mitigation_type is "pause" and self.current_mitigation.include_targets:
			return

		# Paint & populate display
		fill(self.palette['grue'])

		# if in a screen-clearing mitigation, just flip after the fill
		if self.mitigating and self.current_mitigation.mitigation_type is "pause" and self.current_mitigation.clear_screen:
			flip()
			return

		# Spawn & blit PVT display (if PVT event; is None if between events and positive during ITIs)
		if self.time_until_next_trial is 0:
			# Digit string represents milliseconds elapsed since PVT onset
			digit_str = str((now() - self.next_trial_start_time) * 1000)[0:4]
			if digit_str[-1] == ".":
				digit_str = digit_str[0:3]
			digits = message(digit_str, 'PVT_digits', flip_screen=False, blit_txt=False)
			blit(self.assets['PVT_frame'], BL_CENTER, P.screen_c)
			blit(digits, BL_CENTER, P.screen_c)
		# Otherwise, blit cursor to updated position
		else:
			blit(self.assets['fixation'], BL_CENTER, P.screen_c)
			blit(self.assets['inner_ring'], BL_CENTER, P.screen_c)
			blit(self.assets['middle_ring'], BL_CENTER, P.screen_c)
			blit(self.assets['outer_ring'], BL_CENTER, P.screen_c)
			blit(self.assets['cursor'], BL_CENTER, [self.position, P.screen_c[1]])

		# Present display
		flip()

		if debug_this: print "\n<<< __render() <<<"

	def __buffeting_force(self):
		"""
		Generates variable buffeting force
		Force equals sum of several sinusoidal functions

		Note: when modifying these values

		value in "sin( val * timestamp)" modifies periodicity of sin wave, but not amplitude
		i.e., how long to reach min/max amplitude, lower vals mean wider/longer periods

		value in "val * sin(timestamp)" modifies amplitude of sin wave, but not periodicity
		i.e., scales resultant displacement value applied to cursor.
		"""
		t = self.current_frame.timestamp
		return sin(t) + sin(0.3 * t) + sin(0.5 * t) + sin(0.7 * t) - sin(0.9 * t)

	def __compute_buffet_modifier_values(self, start=0.1, stop=1.4, count=100):
		"""
		Generates cyclical sequence of modifier terms used to generate additional buffeting forces
		"""

		modifiers = np.tan(np.geomspace(start, stop, count))

		# Make modifier list 'cyclical' by flipping sign & reversing order (also trim end points to remove duplicates)
		flip_and_reverse = np.negative(modifiers[-1:1:-1])

		self.forces['additional'] = np.append(modifiers, flip_and_reverse)

	def __compute_forces(self):
		"""
		Aggregates buffeting forces to be applied on next render
		"""

		self.forces['buffeting'] = self.__buffeting_force()

		# At the time of authorship, the contribution of this force was undecided, but the possibility of it's
		# inclusion has been preserved
		try:
			self.forces['additional'] = self.__additional_force()
		except AttributeError:
			self.forces['additional'] = None
		self.forces['net'] = self.forces['buffeting']

		# update current frame
		self.current_frame.forces = self.forces


	def __capture_mouse_input(self, event_queue):
		"""
		Captures mouse motion events
		"""

		# print "\n\n >>> __capture_mouse_input() >>>"
		if self.mitigating and self.current_mitigation.mitigation_type is "pause":
			return

		for event in event_queue:
			if event.type == sdl2.SDL_MOUSEMOTION:
				if self.supervise_input:
					if -self.max_input_step < event.motion.xrel < self.max_input_step:
						self.current_frame.user_input = event.motion.xrel
					elif event.motion.xrel < -self.max_input_step:
						self.current_frame.user_input = -self.max_input_step
					else:
						self.current_frame.user_input = self.max_input_step
				else:
					self.current_frame.user_input = event.motion.xrel

		# if no mouse activity was detected, assign an integer anyway
		if self.current_frame.user_input is None:
			self.current_frame.user_input = 0
		self.current_frame.user_input *= 1.0  # just make sure it's a float

		# Maintain mouse cursor at screen center to ensure all movement is catchable (i.e., can't run off screen)
		mouse_pos(False, P.screen_c)

		# print "\n<<<__capture_mouse_input() <<<"
		return self.current_frame.user_input


	@property
	def position(self):
		"""
		Gets current position of cursor.
		"""
		return self._position


	@position.setter
	def position(self, val):
		"""
		Set position of cursor, censors values which would place the cursor off screen
		"""
		if int(val) not in range(*self.x_bounds):
			if val < self.x_bounds[0]:
				val = self.x_bounds[0]
			else:
				val = self.x_bounds[1]

		self._position = val

	@property
	def next_trial_start_time(self):
		return self.__next_trial_start_time

	@next_trial_start_time.setter
	def next_trial_start_time(self, val):
		self.__next_trial_start_time = val

	@property
	def time_until_next_trial(self):
		# if the value is None, we are between trials
		if self.__next_trial_start_time is None:
			raise ValueError('No trial scheduled')

		# if the value is zero, a PVT is currently active
		if now() > self.__next_trial_start_time:
			return 0

		# else, just give the actual value
		return self.__next_trial_start_time - now()

	@property
	def current_frame(self):
		return self.frames[P.trial_number - 1][-1]


class CompTrackFrame(EnvAgent):
	def __init__(self, id, timestamp):
		super(CompTrackFrame, self).__init__()
		self.id = id
		self.participant_id = P.participant_id
		self.trial_number = P.trial_number
		self.block_number = P.block_number
		self.__timestamp = timestamp
		self.user_input = -1
		self.displacement = -1
		self.rt = -1
		self.forces = {'buffeting': -1, 'additional': -1, 'net': -1}
		self.target_position = -1  # note: at end, i.e, post forces & input


	def dump(self, verbose=False):
		data = [P.participant_id, self.block_number, self.trial_number, self.timestamp,
				self.forces['buffeting'], self.forces['additional'], self.forces['net'],
				self.user_input, self.target_position, self.displacement, self.rt]
		labels = ['participant_id','block_num', 'trial_num', 'timestamp', 'buffeting_force', 'additional_force', 'net_force',
				  'user_input', 'target_position','displacement', 'rt']
		if verbose:
			dump_str = ''
			for i in range(0, len(labels)):
				dump_str += "{0}: {1} |\t".format(labels[i], data[i])

			return dump_str

		return {labels[i]:data[i] for i in range(0, len(labels))}

	@property
	def timestamp(self):
		return float(self.__timestamp)


class CompTrackAssessment(EnvAgent):
	def __init__(self, mean_rt=None, lapses=None):
		super(CompTrackAssessment, self).__init__()
		self.timestamp = now()
		self.lapses = lapses
		self.mean_rt = None
		self.participant_id = P.participant_id
		self.trial_number = P.trial_number
		self.samples = P.assessment_sample_size
		self.block_number = P.block_number

	def dump(self):
		# note: sequence is important as it mirrors the corresponding data table
		return [self.participant_id, self.trial_number, self.block_number, self.timestamp,  self.mean_rt,self.lapses,  self.samples]


def mitigation_label(mitigation):
	return "T{).{}_end".format(P.trial_number, mitigation)


class CompTrackMitigation(EnvAgent):
	def __init__(self):
		super(CompTrackMitigation, self).__init__()
		self.comp_track = None  # required
		self.mitigation_type = None
		self.message = None  # if set to a function, will be called on run()

	@abc.abstractmethod
	def run(self):
		pass

	@abc.abstractmethod
	def update(self):
		pass



class AudioMitigation(CompTrackMitigation):
	def __init__(self, comp_track, tone_file_path, duration):
		super(AudioMitigation, self).__init__()
		self.comp_track = comp_track
		self.tone = AudioClip(tone_file_path)
		self.duration = duration
		self.mitigation_type = "audio"

	def run(self):
		try:
			self.message()
		except AttributeError:
			pass
		self.comp_track.mitigating = True
		self.tone.play()
		self.ends_at = now() + self.duration

	def update(self):
		"""
		As we don't wish to lock-up the system while the tone plays, it is the responsibility of the CompTrack object to
		call this in it's loop.
		"""
		if now() < self.ends_at:
			return
		self.tone.stop()
		self.comp_track.__clear_mitigations()

class PauseMitigation(CompTrackMitigation):
	def __init__(self, comp_track, duration, clear_screen, pause_target=False):
		super(PauseMitigation, self).__init__()
		self.comp_track = comp_track
		self.duration = duration
		self.include_target = pause_target
		self.mitigation_type = "pause"
		self.clear_screen = clear_screen
		self.ends_at = None


	def run(self):
		try:
			self.message()
		except AttributeError:
			pass
		self.ends_at = now() + self.duration

	def update(self):
		if now() < self.ends_at:
			return
		self.comp_track.__clear_mitigations()


class RampMitigation(CompTrackMitigation):
	def __init__(self, comp_track, factors_cfg, duration):
		super(RampMitigation, self).__init__()
		self.comp_track = comp_track
		self.duration = duration
		self.factors_cfg = factors_cfg
		self.onset = None
		self.mitigation_type = "ramp"
		self.factor_initial_values = []
		self.ends_at = None

	def run(self):
		self.onset = now()
		try:
			self.message()
		except AttributeError:
			pass
		# save a copy of initial value so they an be restored
		for f in self.factors_cfg:
			f_name = f['factor']
			self.factor_initial_values.append([f_name, self.comp_track[f_name]])
		self.ends_at = now() + self.duration

	def update(self):
		if now() < self.ends_at:
			for f in self.factors_cfg:
				f_name = f['factor']
				try:
					# if the delta is a function, pass it the elapsed time and set the comp track value to it's rturn
					self.comp_track[f_name] = f['change_with'](self.elapsed)
				except AttributeError:
					# if the delta is a goal state, infer current value
					goal_diff = f['change_to'] - self.factor_initial_values[f_name]
					progression = self.elapsed() / self.duration
					self.comp_track[f_name] =  progression * goal_diff
			return

		self.comp_track.__clear_mitigations()

	@property
	def elapsed(self):
		return now() - self.onset