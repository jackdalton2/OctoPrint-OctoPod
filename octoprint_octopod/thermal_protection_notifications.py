import time

from .alerts import Alerts


class ThermalProtectionNotifications:

	def __init__(self, logger, ifttt_alerts):
		self._logger = logger
		self._ifttt_alerts = ifttt_alerts
		self._alerts = Alerts(self._logger)
		self._last_thermal_runaway_notification_time = None  # Variable used for spacing notifications

	def check_temps(self, settings, printer):
		temps = printer.get_current_temperatures()
		# self._logger.debug(u"CheckTemps(): %r" % (temps,))
		if not temps:
			# self._logger.debug(u"No Temperature Data")
			return

		# example dictionary from octoprint
		# {
		#   'bed': {'actual': 0.9, 'target': 0.0, 'offset': 0},
		#   'tool0': {'actual': 0.0, 'target': 0.0, 'offset': 0},
		#   'tool1': {'actual': 0.0, 'target': 0.0, 'offset': 0}
		# }
		thermal_threshold = settings.get_int(['thermal_runway_threshold'])
		thermal_threshold_minutes_frequency = settings.get_int(['thermal_threshold_minutes_frequency'])

		if thermal_threshold > 0:
			# Check for possible thermal runaway
			for k in temps.keys():
				self.__check_thermal_runway(temps, k, thermal_threshold, thermal_threshold_minutes_frequency, settings)

	def __check_thermal_runway(self, temps, part, thermal_threshold, thermal_threshold_minutes_frequency, settings):
		if temps[part]['target'] and temps[part]['target'] > 0:
			# Check if there is a possible thermal runaway
			if temps[part]['actual'] >= (temps[part]['target'] + thermal_threshold):
				last_time = self._last_thermal_runaway_notification_time
				should_alert = not last_time or time.time() > last_time + (thermal_threshold_minutes_frequency * 60)
				if should_alert:
					self._logger.debug("Possible thermal runaway detected for {0}. Actual {1} and Target {2} ".
										format(part, temps[part]['actual'], temps[part]['target']))
					self.__send__thermal_notification(settings, "thermal-runaway")
					self._last_thermal_runaway_notification_time = time.time()

	def __send__thermal_notification(self, settings, event_code):
		# Fire IFTTT webhook
		self._ifttt_alerts.fire_event(settings, event_code, "")
		# Send push notification via OctoPod app
		self.__send__octopod_notification(settings, event_code)

	def __send__octopod_notification(self, settings, event_code):
		server_url = settings.get(["server_url"])
		if not server_url or not server_url.strip():
			# No APNS server has been defined so do nothing
			return -1

		tokens = settings.get(["tokens"])
		if len(tokens) == 0:
			# No iOS devices were registered so skip notification
			return -2

		# For each registered token we will send a push notification
		# We do it individually since 'printerID' is included so that
		# iOS app can properly render local notification with
		# proper printer name
		used_tokens = []
		last_result = None
		for token in tokens:
			apns_token = token["apnsToken"]

			# Ignore tokens that already received the notification
			# This is the case when the same OctoPrint instance is added twice
			# on the iOS app. Usually one for local address and one for public address
			if apns_token in used_tokens:
				continue
			# Keep track of tokens that received a notification
			used_tokens.append(apns_token)

			if 'printerName' in token and token["printerName"] is not None:
				# We can send non-silent notifications (the new way) so notifications are rendered even if user
				# killed the app
				printer_name = token["printerName"]
				language_code = token["languageCode"]
				url = server_url + '/v1/push_printer'

				last_result = self._alerts.send_alert_code(settings, language_code, apns_token, url, printer_name,
														   event_code, None, None)

		return last_result