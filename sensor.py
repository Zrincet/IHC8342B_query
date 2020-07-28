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

__version__ = '0.1.0'
_LOGGER = logging.getLogger(__name__)

REQUIREMENTS = ['requests', 'beautifulsoup4']

COMPONENT_REPO = 'https://github.com/zrincet/IHC8342B_query/'
SCAN_INTERVAL = timedelta(seconds=300)
CONF_OPTIONS = "options"
CONF_MAC = "mac"

ATTR_NAME = "名称"
ATTR_UPDATE_TIME = "更新时间"
ATTR_DATA_TIME = "数据时间"
ATTR_MAC_ADDR = "MAC地址"

OPTIONS = dict(eleTotal=["IHC8342B_ele_total", "累计用电", "mdi:flash", "kW·h", "fw_hongyanelec_v1"],
               eleHour=["IHC8342B_ele_hour", "小时用电", "mdi:flash", "kW·h", "fw_hydayelec_v1"],
               eleToday=["IHC8342B_ele_today", "今日用电", "mdi:flash", "kW·h", "fw_hongyanelec_v1"],
               eleMonth=["IHC8342B_ele_month", "本月用电", "mdi:flash", "kW·h", "fw_hymonthelec_v1"],
               eleYear=["IHC8342B_ele_year", "年度用电", "mdi:flash", "kW·h", "fw_hyyearelec_v1"],
               power=["IHC8342B_power", "实时功率", "mdi:power-plug-outline", "W", "fw_hongyanelec_v1"])

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_MAC): cv.string,
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_OPTIONS, default=[]): vol.All(cv.ensure_list, [vol.In(OPTIONS)]),
})


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    _LOGGER.info("async_setup_platform sensor IHC8342B Sensor")
    dev = []
    for option in config[CONF_OPTIONS]:
        dev.append(IHC8342BSensor(config[CONF_MAC], config[CONF_NAME], option))

    async_add_devices(dev, True)


class IHC8342BSensor(Entity):
    def __init__(self, mac_user_input, name, option):
        self._macUserInput = mac_user_input
        self._state = None
        self._mac = str(mac_user_input).replace(":", "").replace("：", "").lower()

        self._eleTotal = None
        self._eleToday = None
        self._eleMonth = None
        self._eleYear = None

        self._power = None
        self._dataTime = None
        self._updateTime = None

        self._object_id = OPTIONS[option][0]
        self._friendly_name = str(name) + '_' + OPTIONS[option][1]
        self._icon = OPTIONS[option][2]
        self._unit_of_measurement = OPTIONS[option][3]
        self._type = option

    def update(self):
        import datetime
        import time

        timeNow = (datetime.datetime.utcnow() + datetime.timedelta(hours=8))

        _LOGGER.info("IHC8342B Sensor start updating data.")
        header = {
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'okhttp/3.11.0'
        }
        url = 'https://hongyan.ibroadlink.com/dataservice/v2/device/status'

        data = {
            "report": "fw_hongyanelec_v1",
            "device": [
                {
                    "did": "00000000000000000000" + self._mac,
                    "params": ["power", "elec", "occurtime"],
                    "start": timeNow.strftime("%Y-%m-%d_00:00:00"),
                    "end": timeNow.strftime("%Y-%m-%d_23:59:59")
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
            self._eleTotal = float(re_json['table'][0]['values'][0]['elec'])/100
            self._power = float(re_json['table'][0]['values'][0]['power'])/100
            self._eleToday = float(re_json['table'][0]['values'][0]['elec'])/100 - float(re_json['table'][0]['values'][-1]['elec'])/100
            self._dataTime = str(re_json['table'][0]['values'][0]['occurtime']).replace("_", " ")

            self._updateTime = timeNow.strftime("%Y-%m-%d %H:%M:%S")

            if self._type == "eleTotal":
                self._state = self._eleTotal
            elif self._type == "eleToday":
                self._state = self._eleToday
            elif self._type == "power":
                self._state = self._power
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
        return {
            ATTR_UPDATE_TIME: self._updateTime,
            ATTR_DATA_TIME: self._dataTime,
            ATTR_MAC_ADDR: self._mac
        }
