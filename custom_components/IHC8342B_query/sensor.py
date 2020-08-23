#!/usr/bin/env python 
# -*- coding:utf-8 -*-
"""
A component which allows you to parse HonYar_server get IHC8342B's electricity info

For more details about this component, please refer to the documentation at
https://github.com/zrincet/IHC8342B_query/

"""
import logging
import asyncio
import voluptuous as vol
from datetime import timedelta
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import (PLATFORM_SCHEMA)
from homeassistant.const import (CONF_NAME)
import requests
from requests.exceptions import (
    ConnectionError as ConnectError, HTTPError, Timeout)
from bs4 import BeautifulSoup
import json

__version__ = '1.1.2'
_LOGGER = logging.getLogger(__name__)

REQUIREMENTS = ['requests', 'beautifulsoup4']

COMPONENT_REPO = 'https://github.com/zrincet/IHC8342B_query/'
SCAN_INTERVAL = timedelta(seconds=300)
CONF_OPTIONS = "options"
CONF_MAC = "mac"
CONF_PRICE = "price"

ATTR_NAME = "名称"
ATTR_UPDATE_TIME = "更新时间"
ATTR_DATA_TIME = "数据时间"
ATTR_MAC_ADDR = "MAC地址"
ATTR_PRICE = "电费"

OPTIONS = dict(eleTotal=["IHC8342B_ele_total", "累计用电", "mdi:flash", "kW·h", "fw_hongyanelec_v1"],
               # eleHour=["IHC8342B_ele_hour", "小时用电", "mdi:flash", "kW·h", "fw_hydayelec_v1"],  #  no useful
               eleToday=["IHC8342B_ele_today", "今日用电", "mdi:flash", "kW·h", "fw_hongyanelec_v1"],
               eleMonth=["IHC8342B_ele_month", "本月用电", "mdi:flash", "kW·h", "fw_hymonthelec_v1"],
               eleYear=["IHC8342B_ele_year", "年度用电", "mdi:flash", "kW·h", "fw_hyyearelec_v1"],
               power=["IHC8342B_power", "实时功率", "mdi:power-plug-outline", "W", "fw_hongyanelec_v1"])

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_MAC): cv.string,
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_PRICE, default=0.53): cv.string,
    vol.Required(CONF_OPTIONS, default=['eleTotal']): vol.All(cv.ensure_list, [vol.In(OPTIONS)]),
})


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    _LOGGER.info("async_setup_platform sensor IHC8342B Sensor")
    dev = []
    for option in config[CONF_OPTIONS]:
        dev.append(IHC8342BSensor(config[CONF_MAC], config[CONF_NAME], config[CONF_PRICE], option))

    async_add_devices(dev, True)


class IHC8342BSensor(Entity):
    def __init__(self, mac_user_input, name, price, option):
        self._macUserInput = mac_user_input
        self._state = 0.0
        self._mac = str(mac_user_input).replace(":", "").replace("：", "").lower()
        self._price = float(price)

        self._eleTotal = 0.0
        self._eleToday = 0.0
        self._eleMonth = 0.0
        self._eleYear = 0.0

        self._startTime = None
        self._endTime = None

        self._power = 0.0
        self._dataTime = 'None'
        self._updateTime = 'None'

        self._object_id = OPTIONS[option][0]
        self._friendly_name = str(name) + '_' + OPTIONS[option][1]
        self._icon = OPTIONS[option][2]
        self._unit_of_measurement = OPTIONS[option][3]
        self._postType = OPTIONS[option][4]
        self._type = option

    def update(self):
        import datetime
        import time
        import calendar

        timeNow = (datetime.datetime.utcnow() + datetime.timedelta(hours=8))
        monthRange = calendar.monthrange(timeNow.year, timeNow.month)[1]

        _LOGGER.info("IHC8342B Sensor start updating data.")
        header = {
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'okhttp/3.11.0'
        }
        if self._type == "eleTotal" or self._type == "eleToday" or self._type == "power":
            url = 'https://hongyan.ibroadlink.com/dataservice/v2/device/status'
            self._startTime = timeNow.strftime("%Y-%m-%d_00:00:00")
            self._endTime = timeNow.strftime("%Y-%m-%d_23:59:59")

        elif self._type == "eleMonth":
            url = 'https://hongyan.ibroadlink.com/dataservice/v2/device/stats'
            self._startTime = timeNow.strftime("%Y-%m-01_00:00:00")
            self._endTime = timeNow.strftime("%Y-%m-day_23:59:59").replace("day", str(monthRange))

        elif self._type == "eleYear":
            url = 'https://hongyan.ibroadlink.com/dataservice/v2/device/stats'
            self._startTime = timeNow.strftime("%Y-01-01_00:00:00")
            self._endTime = timeNow.strftime("%Y-12-31_23:59:59")

        data = {
            "report": self._postType,
            "device": [
                {
                    "did": "00000000000000000000" + self._mac,
                    "params": ["power", "elec", "occurtime"],
                    "start": self._startTime,
                    "end": self._endTime
                }
            ]
        }
        try:
            response = requests.post(url, headers=header, json=data)
            re_json = json.loads(response.text)
        except (ConnectError, HTTPError, Timeout, ValueError) as error:
            time.sleep(0.01)
            _LOGGER.error("Unable to connect to HonYar server. %s", error)

        try:

            self._dataTime = str(re_json['table'][0]['values'][0]['occurtime']).replace("_", " ")

            self._updateTime = timeNow.strftime("%Y-%m-%d %H:%M:%S")

            if self._type == "eleTotal":
                self._eleTotal = float(re_json['table'][0]['values'][0]['elec']) / 100
                self._state = self._eleTotal

            elif self._type == "eleToday":
                self._eleToday = round(float(re_json['table'][0]['values'][0]['elec']) / 100 - float(
                    re_json['table'][0]['values'][-1]['elec']) / 100, 2)
                self._state = self._eleToday

            elif self._type == "power":
                self._power = float(re_json['table'][0]['values'][0]['power']) / 100
                self._state = self._power

            elif self._type == "eleMonth":
                # 当今天为1号时按照普通情况处理
                if timeNow.day == 1 or len(re_json['table'][0]['values']) != 1:
                    endEle = float(re_json['table'][0]['values'][-1]['elec']) / 100
                    data['report'] = 'fw_hydayelec_v1'
                    data['device'][0]['start'] = timeNow.strftime("%Y-%m-01_00:00:00")
                    data['device'][0]['end'] = timeNow.strftime("%Y-%m-01_23:59:59")

                    try:
                        response = requests.post(url, headers=header, json=data)
                        re_json = json.loads(response.text)
                    except (ConnectError, HTTPError, Timeout, ValueError) as error:
                        time.sleep(0.01)
                        _LOGGER.error("Unable to connect to HonYar server. %s", error)

                    startEle = float(re_json['table'][0]['values'][0]['elec']) / 100

                    self._eleMonth = round(endEle - startEle, 2)

                # 新插排第一天入网的情况
                elif len(re_json['table'][0]['values']) == 1:
                    self._eleMonth = float(re_json['table'][0]['values'][0]['elec']) / 100

                self._state = self._eleMonth
                self._dataTime = str(re_json['table'][0]['values'][0]['occurtime']).split("_")[0] + " - " + str(
                    re_json['table'][0]['values'][-1]['occurtime']).split("_")[0]

            elif self._type == "eleYear":
                if len(re_json['table'][0]['values']) == 1:
                    self._eleYear = float(re_json['table'][0]['values'][0]['elec']) / 100
                else:
                    endEle = float(re_json['table'][0]['values'][-1]['elec']) / 100
                    startMonth = str(re_json['table'][0]['values'][0]['occurtime']).split("-")[1]
                    data['report'] = 'fw_hymonthelec_v1'
                    data['device'][0]['start'] = timeNow.strftime("%Y-month-01_00:00:00").replace("month", startMonth)
                    monthRange = calendar.monthrange(timeNow.year, int(startMonth))[1]
                    data['device'][0]['end'] = timeNow.strftime("%Y-month-day_23:59:59").replace("day", str(monthRange)).replace("month", startMonth)

                    try:
                        response = requests.post(url, headers=header, json=data)
                        re_json = json.loads(response.text)
                    except (ConnectError, HTTPError, Timeout, ValueError) as error:
                        time.sleep(0.01)
                        _LOGGER.error("Unable to connect to HonYar server. %s", error)

                    startEle = float(re_json['table'][0]['values'][0]['elec']) / 100

                    self._eleYear = round(endEle-startEle, 2)
                self._state = self._eleYear
                self._dataTime = str(re_json['table'][0]['values'][0]['occurtime']).split("_")[0] + " - " + str(
                    re_json['table'][0]['values'][-1]['occurtime']).split("_")[0]

        except Exception as e:
            _LOGGER.error("Something wrong in IHC8342B sensor. %s", e.args[0])

    @property
    def name(self):
        return self._friendly_name

    @property
    def state(self):
        return self._state

    @property
    def icon(self):
        return self._icon

    @property
    def unique_id(self):
        return self._object_id

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def device_state_attributes(self):
        if self._type == "power":
            return {
                ATTR_UPDATE_TIME: self._updateTime,
                ATTR_DATA_TIME: self._dataTime,
                ATTR_MAC_ADDR: self._mac,
            }
        else:
            return {
                ATTR_UPDATE_TIME: self._updateTime,
                ATTR_DATA_TIME: self._dataTime,
                ATTR_MAC_ADDR: self._mac,
                ATTR_PRICE: "%.2f元" % round(self._state * self._price, 2)
            }
