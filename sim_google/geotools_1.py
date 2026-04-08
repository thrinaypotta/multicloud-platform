from datetime import datetime

class GeoPoint(object):

    __counter = 0

    def __init__(self, lat: float | int, lon: float | int, name: str = "GeoPoint"):
        self.__latitude, self.__longitude = None, None
        self.name = name
        self.set_latitude(lat)
        self.set_longitude(lon)
        GeoPoint.__counter += 1

    def set_latitude(self, lat: float | int):
        if not isinstance(lat, (float, int)):
            raise ValueError(f"latitude must be a float or int, instead of {type(lat)}!")
        if not -90.0 <= lat <= 90.0:
            raise ValueError(f"latitude must be between -90.0 and 90.0, instead of {lat}!")
        self.__latitude = lat

    def set_longitude(self, lon: float | int):
        if not isinstance(lon, (float, int)):
            raise ValueError(f"longitude must be a float or int, instead of {type(lon)}!")
        if not -180.0 <= lon <= 180.0:
            raise ValueError(f"longitude must be between -180.0 and 180.0, instead of {lon}!")
        self.__longitude = lon

    def get_latitude(self):
        return self.__latitude

    def get_longitude(self):
        return self.__longitude

    def get_coordinates(self):
        return (self.__latitude, self.__longitude)

    def __str__(self):
        return f"{self.name}: ({self.get_latitude()}, {self.get_longitude()})"

    def __del__(self):
        GeoPoint.__counter -= 1

    @classmethod
    def get_counter(cls):
        return cls.__counter

    @staticmethod
    def to_dms(value: float | int) -> tuple:
        """
        it converts decimal degrees to degrees, minutes and seconds.
        :param value: decimal degrees
        :return: (degrees, minutes, seconds)
        """
        if not isinstance(value, (float, int)):
            raise ValueError(f"value must be a float or int, instead of {type(value)}!")
        degrees = int(value)
        minutes = int((value - degrees) * 60.0)
        seconds = ((value - degrees) * 60.0 - minutes) * 60.0
        return degrees, minutes, seconds

    @staticmethod
    def to_dd(degrees: float | int, minutes: float | int, seconds: float | int) -> float:
        """
        it converts degrees, minutes and seconds to decimal degrees.
        :param degrees:
        :param minutes:
        :param seconds:
        :return:
        """
        if not all((isinstance(param, (float, int)) for param in (degrees, minutes, seconds))):
            raise ValueError(f"values must be float or int!")
        return degrees + minutes/60.0 + seconds/3600.0



class GNSSPosition(GeoPoint):

    def __init__(self, lat: float | int, lon: float | int, sats: int | None = None, quality: int | None = None, ts:datetime | None = None, name: str = "GNSSPosition"):
        super().__init__(lat, lon, name=name)
        self.__sats, self.__quality, self.__ts = None, None, None

    def set_timestamp(self, ts: datetime):
        if not isinstance(ts, datetime):
            raise ValueError(f"timestamp must be a datetime, instead of {type(ts)}!")
        self.__ts = ts

    def get_timestamp(self):
        return self.__ts

    def set_sats(self, sats: int | None):
        if not isinstance(sats, int):
            raise ValueError(f"sats must be a int, instead of {type(sats)}!")
        if sats < 0:
            raise ValueError(f"sats must be a non-negative int, instead of {sats}!")
        self.__sats = sats

    def get_sats(self):
        return self.__sats

    def set_quality(self, quality: int | None):
        if not isinstance(quality, int):
            raise ValueError(f"quality must be a int, instead of {type(quality)}!")
        if not 0 <= quality <= 7:
            raise ValueError(f"quality must be between 0 and 7, instead of {quality}!")
        self.__quality = quality

    def get_quality(self):
        return self.__quality

    def __str__(self):
        return f"{self.name}: ({self.get_latitude()}, {self.get_longitude()}, {self.get_sats()}, {self.get_quality()})"

if __name__ == "__main__":
    p1 = GeoPoint(52.55, 13.55)
    p2 = GeoPoint(53.50, 9.99)

    p3 = GNSSPosition(52.55, 13.55)
    p4 = GNSSPosition(53.50, 9.99)

    """
    print(isinstance(p1, GeoPoint))
    print(isinstance(p3, GeoPoint))
    print(isinstance(p1, GNSSPosition))
    print(isinstance(p3, GNSSPosition))
    """

    print(GNSSPosition.get_counter())
    print(GeoPoint.get_counter())