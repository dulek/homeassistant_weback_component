"""
VacDevice Module
"""

import io
import logging

from .vacmap import VacMap, VacMapDraw
from .webackapi import WebackWssCtrl

_LOGGER = logging.getLogger(__name__)


class VacDevice(WebackWssCtrl):
    """
    VacDevice Class
    """

    def __init__(
        self,
        thing_name,
        thing_nickname,
        sub_type,
        thing_status,
        user,
        password,
        region,
        country,
        app,
        client_id,
        api_version,
    ):
        _LOGGER.debug("WebackApi RobotController __init__")
        super().__init__(user, password, region, country, app, client_id, api_version)
        self.name = thing_name
        self.nickname = thing_nickname
        self.sub_type = sub_type
        self.map = None
        self.map_image_buffer = None
        self.map_camera = None

        # First init status from HTTP API
        if self.robot_status is None:
            self.robot_status = thing_status

    # ==========================================================
    # Update controller

    async def watch_state(self):
        """State watcher from VacDevice"""
        _LOGGER.debug(
            "VacDevice: starting state watcher for= %s (%s)", self.name, self.sub_type
        )
        try:
            await self.refresh_handler(self.name, self.sub_type)
        except Exception as watch_excpt:
            _LOGGER.exception(
                "Error on watch_state starting refresh_handler %s", watch_excpt
            )

    async def load_maps(self):
        """Load the current reuse map"""

        if self.ACTIVE_MAP_ID_PROP not in self.robot_status:
            return False

        map_data = await self.get_reuse_map_by_id(
            self.robot_status[self.ACTIVE_MAP_ID_PROP], self.sub_type, self.name
        )
        if map_data:
            self.map = VacMap(map_data)
            self.render_map()

    def render_map(self):
        """Rendering Map"""
        if not self.map:
            return False

        vac_map_draw = VacMapDraw(self.map)
        vac_map_draw.draw_charger_point()
        vac_map_draw.draw_path()
        vac_map_draw.draw_robot_position()

        img = vac_map_draw.get_image()

        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        img.close()
        self.map_image_buffer = img_byte_arr.getvalue()

        if self.map_camera is not None:
            self.trigger_map_camera_update()

        return True

    def register_map_camera(self, camera):
        """Register map camera"""
        self.map_camera = camera

    def trigger_map_camera_update(self):
        """Trigger map camera update"""
        if self.map_camera is not None:
            self.map_camera.schedule_update_ha_state(True)

    # ==========================================================
    # Vacuum Entity
    # -> Properties

    @property
    def current_mode(self):
        """Raw working_status field string"""
        if "working_status" in self.robot_status:
            return self.robot_status["working_status"]
        return self.IDLE_MODE

    @property
    def raw_status(self) -> str:
        """Raw thing_status JSON"""
        _LOGGER.debug("raw_status %s", self.robot_status)
        return self.robot_status

    @property
    def is_cleaning(self) -> bool:
        """Boolean define if robot is in cleaning state"""
        _LOGGER.debug("is_cleaning = %s ", self.current_mode)
        return self.current_mode in self.CLEANING_STATES

    @property
    def is_available(self):
        """Boolean define if robot is connected to cloud"""
        connected = self.robot_status.get("connected")
        return connected == "true" if connected is not None else False

    @property
    def is_charging(self):
        """Boolean define if robot is charging"""
        return self.current_mode in self.CHARGING_STATES

    @property
    def error_info(self):
        """Raw error_info field string"""
        if "error_info" in self.robot_status:
            return self.robot_status["error_info"]
        return None

    @property
    def battery_level(self):
        """Raw battery_level field integer"""
        if "battery_level" in self.robot_status:
            return int(self.robot_status["battery_level"])
        return 0

    @property
    def fan_status(self):
        """Raw fan_status field string"""
        if "fan_status" in self.robot_status:
            return self.robot_status["fan_status"]
        return None

    @property
    def mop_status(self):
        """Raw fan_status field string"""
        if "water_level" in self.robot_status:
            return self.robot_status["water_level"]
        return None

    @property
    def fan_speed_list(self):
        """Return Fan speed list available"""
        return [self.FAN_SPEED_QUIET, self.FAN_SPEED_NORMAL, self.FAN_SPEED_HIGH]

    @property
    def mop_level_list(self):
        """Return Mop level list available"""
        return [self.MOP_SPEED_LOW, self.MOP_SPEED_NORMAL, self.MOP_SPEED_HIGH]

    @property
    def clean_time(self):
        """Return clean time"""
        if "clean_time" in self.robot_status:
            return self.robot_status["clean_time"]
        return 0

    @property
    def clean_area(self):
        """Return clean area in square meter"""
        if "clean_area" in self.robot_status:
            return self.robot_status["clean_area"]
        return 0

    @property
    def vacuum_or_mop(self) -> int:
        """Find if the robot is in vacuum or mop mode"""
        if "fan_status" and "water_level" in self.robot_status:
            if (
                self.robot_status["fan_status"] == self.FAN_DISABLED
                and self.robot_status["water_level"] != self.MOP_DISABLED
            ):
                return self.MOP_ON
            return self.VACUUM_ON
        return self.NO_FAN_NO_MOP

    # ==========================================================
    # Vacuum Entity
    # -> Method

    async def set_fan_water_speed(self, speed):
        """User for set both : fan speed and water level"""
        # Checking if robot is running otherwise it will not apply value
        if not self.is_cleaning:
            _LOGGER.info(
                "Vacuum: Can't set set fan/water speed (value=%s) robot is not running.",
                speed,
            )
            return
        # Checking value are allowed
        if speed not in self.FAN_SPEEDS and speed not in self.MOP_SPEEDS:
            _LOGGER.error("Error: Fan/Mop value=%s is not available", speed)
            return
        # Sending command
        working_payload = {self.SET_FAN_SPEED: speed}
        await self.send_command(self.name, self.sub_type, working_payload)
        return

    async def turn_on(self):
        """Turn ON vacuum"""
        working_payload = {self.ASK_STATUS: self.CLEAN_MODE_AUTO}
        await self.send_command(self.name, self.sub_type, working_payload)
        return

    async def turn_off(self):
        """Turn OFF vacuum"""
        working_payload = {self.ASK_STATUS: self.CHARGE_MODE_RETURNING}
        await self.send_command(self.name, self.sub_type, working_payload)
        return

    async def pause(self):
        """Pause vacuum"""
        working_payload = {self.ASK_STATUS: self.CLEAN_MODE_STOP}
        await self.send_command(self.name, self.sub_type, working_payload)
        return

    async def clean_spot(self):
        """Clean spot command"""
        working_payload = {self.ASK_STATUS: self.CLEAN_MODE_SPOT}
        await self.send_command(self.name, self.sub_type, working_payload)
        return

    async def locate(self):
        """Locate vacuum"""
        working_payload = {self.ASK_STATUS: self.ROBOT_LOCATION_SOUND}
        await self.send_command(self.name, self.sub_type, working_payload)
        return

    async def return_to_base(self):
        """Return to base command"""
        working_payload = {self.ASK_STATUS: self.CHARGE_MODE_RETURNING}
        await self.send_command(self.name, self.sub_type, working_payload)
        return

    async def goto(self, point: str):
        """GoTo point command"""
        working_payload = {
            self.ASK_STATUS: self.ROBOT_PLANNING_LOCATION,
            self.GOTO_POINT: point,
        }
        await self.send_command(self.name, self.sub_type, working_payload)
        return

    async def clean_rect(self, rectangle: str):
        """Clean rectangle command"""
        working_payload = {
            self.ASK_STATUS: self.ROBOT_PLANNING_RECT,
            self.RECTANGLE_INFO: rectangle,
        }
        await self.send_command(self.name, self.sub_type, working_payload)
        return

    async def voice_mode(self, state: str):
        """Voice mode"""
        if state in self.SWITCH_VALUES:
            working_payload = {self.VOICE_SWITCH: state}
            await self.send_command(self.name, self.sub_type, working_payload)
        else:
            _LOGGER.error("Voice mode can't be set with value : %s ", state)
        return

    async def undisturb_mode(self, state: str):
        """Undisturb mode"""
        if state in self.SWITCH_VALUES:
            working_payload = {self.UNDISTURB_MODE: state}
            await self.send_command(self.name, self.sub_type, working_payload)
        else:
            _LOGGER.error("Undisturb mode can't be set with value : %s ", state)
        return

    async def clean_room(self, room_ids_list: list):
        """Clean room command"""
        room_data = []
        for room_id in room_ids_list:
            room_data.append(dict(room_id=room_id))
        working_payload = {
            self.ASK_STATUS: self.CLEAN_MODE_ROOMS,
            self.SELECTED_ZONE: room_data,
        }
        await self.send_command(self.name, self.sub_type, working_payload)

    async def clean_zone(self, bounding):
        """Clean zone command"""
        box_x = []
        box_y = []
        num_boxes = len(bounding)

        for box in bounding:
            box_x.append(int(box[0] / 10))
            box_x.append(int(box[0] / 10))
            box_x.append(int(box[2] / 10))
            box_x.append(int(box[2] / 10))
            box_y.append(int(box[1] / 10))
            box_y.append(int(box[3] / 10))
            box_y.append(int(box[3] / 10))
            box_y.append(int(box[1] / 10))

        working_payload = {
            self.ASK_STATUS: self.ROBOT_PLANNING_RECT,
            self.PLANNING_RECT_POINT_NUM: num_boxes * 4,
            self.PLANNING_RECT_X: box_x,
            self.PLANNING_RECT_Y: box_y,
        }
        _LOGGER.debug("Vacuum : Planning rect sent %s", working_payload)
        await self.send_command(self.name, self.sub_type, working_payload)
