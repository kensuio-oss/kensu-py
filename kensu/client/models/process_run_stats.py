# coding: utf-8

"""
    

    No description provided (generated by Swagger Codegen https://github.com/swagger-api/swagger-codegen)

    OpenAPI spec version: beta
    
    Generated by: https://github.com/swagger-api/swagger-codegen.git
"""


from pprint import pformat

from six import iteritems


class ProcessRunStats(object):
    """
    NOTE: This class is auto generated by the swagger code generator program.
    Do not edit the class manually.
    """


    """
    Attributes:
      swagger_types (dict): The key is attribute name
                            and the value is attribute type.
      attribute_map (dict): The key is attribute name
                            and the value is json key in definition.
    """
    swagger_types = {
        'pk': 'ProcessRunStatsPK',
        'metrics': 'str'
    }

    attribute_map = {
        'pk': 'pk',
        'metrics': 'metrics'
    }

    def __init__(self, pk=None, metrics=None):
        """
        ProcessRunStats - a model defined in Swagger
        """

        self._pk = None
        self._metrics = None

        self.pk = pk
        self.metrics = metrics

    @property
    def pk(self):
        """
        Gets the pk of this ProcessRunStats.

        :return: The pk of this ProcessRunStats.
        :rtype: ProcessRunStatsPK
        """
        return self._pk

    @pk.setter
    def pk(self, pk):
        """
        Sets the pk of this ProcessRunStats.

        :param pk: The pk of this ProcessRunStats.
        :type: ProcessRunStatsPK
        """
        if pk is None:
            raise ValueError("Invalid value for `pk`, must not be `None`")

        self._pk = pk

    @property
    def metrics(self):
        """
        Gets the metrics of this ProcessRunStats.
        Any metrics to be added as a JSON string

        :return: The metrics of this ProcessRunStats.
        :rtype: str
        """
        return self._metrics

    @metrics.setter
    def metrics(self, metrics):
        """
        Sets the metrics of this ProcessRunStats.
        Any metrics to be added as a JSON string

        :param metrics: The metrics of this ProcessRunStats.
        :type: str
        """
        if metrics is None:
            raise ValueError("Invalid value for `metrics`, must not be `None`")

        self._metrics = metrics

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
        if not isinstance(other, ProcessRunStats):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """
        Returns true if both objects are not equal
        """
        return not self == other
