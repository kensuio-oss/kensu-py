# coding: utf-8

from pprint import pformat

from six import iteritems

class LogicalDataSourcePK(object):

    """
    Attributes:
      swagger_types (dict): The key is attribute name
                            and the value is attribute type.
      attribute_map (dict): The key is attribute name
                            and the value is json key in definition.
    """
    swagger_types = {
        'location': 'str',
        'name': 'str'
    }

    attribute_map = {
        'location': 'location',
        'name': 'name'
    }

    def __init__(self, location=None, name=None):
        """
        LogicalDataSourcePK - a model defined in Swagger
        """

        self._location = None
        self._name = None

        self.location = location
        self.name = name

    @property
    def location(self):
        """
        Gets the location of this LogicalDataSourcePK.
        fully qualified location of the datasource, must be unique

        :return: The location of this LogicalDataSourcePK.
        :rtype: str
        """
        return self._location

    @location.setter
    def location(self, location):
        """
        Sets the location of this LogicalDataSourcePK.
        fully qualified location of the datasource, must be unique

        :param location: The location of this LogicalDataSourcePK.
        :type: str
        """
        if location is None:
            raise ValueError("Invalid value for `location`, must not be `None`")

        self._location = location

    @property
    def name(self):
        """
        Gets the name of this LogicalDataSourcePK.
        :return: The name of this LogicalDataSourcePK.
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """
        Sets the name of this LogicalDataSourcePK.

        :param name: The name of this LogicalDataSourcePK.
        :type: str
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")

        self._name = name

    def to_dict(self):
        """
        Returns the model properties as a dict
        """
        result = {}

        for attr, _ in iteritems(self.swagger_types):
            value = getattr(self, attr)
            if isinstance(value, list):
                result[attr] = list(map(
                    lambda x: x.to_dict() if hasattr(x, "to_dict") else x,
                    value
                ))
            elif hasattr(value, "to_dict"):
                result[attr] = value.to_dict()
            elif isinstance(value, dict):
                result[attr] = dict(map(
                    lambda item: (item[0], item[1].to_dict())
                    if hasattr(item[1], "to_dict") else item,
                    value.items()
                ))
            else:
                result[attr] = value

        return result

    def to_str(self):
        """
        Returns the string representation of the model
        """
        return pformat(self.to_dict())

    def __repr__(self):
        """
        For `print` and `pprint`
        """
        return self.to_str()

    def __eq__(self, other):
        """
        Returns true if both objects are equal
        """
        if not isinstance(other, LogicalDataSourcePK):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """
        Returns true if both objects are not equal
        """
        return not self == other
