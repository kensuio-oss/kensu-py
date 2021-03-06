# coding: utf-8

"""
    

    No description provided (generated by Swagger Codegen https://github.com/swagger-api/swagger-codegen)

    OpenAPI spec version: beta
    
    Generated by: https://github.com/swagger-api/swagger-codegen.git
"""


from pprint import pformat

from six import iteritems


class BatchEntityReportResult(object):
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
        'errors': 'list[BatchErrorMessage]',
        'num_errors': 'int',
        'num_ingested': 'int'
    }

    attribute_map = {
        'errors': 'errors',
        'num_errors': 'numErrors',
        'num_ingested': 'numIngested'
    }

    def __init__(self, errors=None, num_errors=None, num_ingested=None):
        """
        BatchEntityReportResult - a model defined in Swagger
        """

        self._errors = None
        self._num_errors = None
        self._num_ingested = None

        self.errors = errors
        self.num_errors = num_errors
        self.num_ingested = num_ingested

    @property
    def errors(self):
        """
        Gets the errors of this BatchEntityReportResult.

        :return: The errors of this BatchEntityReportResult.
        :rtype: list[BatchErrorMessage]
        """
        return self._errors

    @errors.setter
    def errors(self, errors):
        """
        Sets the errors of this BatchEntityReportResult.

        :param errors: The errors of this BatchEntityReportResult.
        :type: list[BatchErrorMessage]
        """
        if errors is None:
            raise ValueError("Invalid value for `errors`, must not be `None`")

        self._errors = errors

    @property
    def num_errors(self):
        """
        Gets the num_errors of this BatchEntityReportResult.

        :return: The num_errors of this BatchEntityReportResult.
        :rtype: int
        """
        return self._num_errors

    @num_errors.setter
    def num_errors(self, num_errors):
        """
        Sets the num_errors of this BatchEntityReportResult.

        :param num_errors: The num_errors of this BatchEntityReportResult.
        :type: int
        """
        if num_errors is None:
            raise ValueError("Invalid value for `num_errors`, must not be `None`")

        self._num_errors = num_errors

    @property
    def num_ingested(self):
        """
        Gets the num_ingested of this BatchEntityReportResult.

        :return: The num_ingested of this BatchEntityReportResult.
        :rtype: int
        """
        return self._num_ingested

    @num_ingested.setter
    def num_ingested(self, num_ingested):
        """
        Sets the num_ingested of this BatchEntityReportResult.

        :param num_ingested: The num_ingested of this BatchEntityReportResult.
        :type: int
        """
        if num_ingested is None:
            raise ValueError("Invalid value for `num_ingested`, must not be `None`")

        self._num_ingested = num_ingested

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
        if not isinstance(other, BatchEntityReportResult):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """
        Returns true if both objects are not equal
        """
        return not self == other
