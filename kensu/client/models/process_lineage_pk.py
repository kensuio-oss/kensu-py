# coding: utf-8

"""
    

    No description provided (generated by Swagger Codegen https://github.com/swagger-api/swagger-codegen)

    OpenAPI spec version: beta
    
    Generated by: https://github.com/swagger-api/swagger-codegen.git
"""


from pprint import pformat

from six import iteritems


class ProcessLineagePK(object):
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
        'process_ref': 'ProcessRef',
        'data_flow': 'list[SchemaLineageDependencyDef]'
    }

    attribute_map = {
        'process_ref': 'processRef',
        'data_flow': 'dataFlow'
    }

    def __init__(self, process_ref=None, data_flow=None):
        """
        ProcessLineagePK - a model defined in Swagger
        """

        self._process_ref = None
        self._data_flow = None

        self.process_ref = process_ref
        self.data_flow = data_flow

    @property
    def process_ref(self):
        """
        Gets the process_ref of this ProcessLineagePK.
        Reference to a data activity/process (e.g. `credit_score_job`)

        :return: The process_ref of this ProcessLineagePK.
        :rtype: ProcessRef
        """
        return self._process_ref

    @process_ref.setter
    def process_ref(self, process_ref):
        """
        Sets the process_ref of this ProcessLineagePK.
        Reference to a data activity/process (e.g. `credit_score_job`)

        :param process_ref: The process_ref of this ProcessLineagePK.
        :type: ProcessRef
        """
        if process_ref is None:
            raise ValueError("Invalid value for `process_ref`, must not be `None`")

        self._process_ref = process_ref

    @property
    def data_flow(self):
        """
        Gets the data_flow of this ProcessLineagePK.
        Describes data dependencies between the participated schemas

        :return: The data_flow of this ProcessLineagePK.
        :rtype: list[SchemaLineageDependencyDef]
        """
        return self._data_flow

    @data_flow.setter
    def data_flow(self, data_flow):
        """
        Sets the data_flow of this ProcessLineagePK.
        Describes data dependencies between the participated schemas

        :param data_flow: The data_flow of this ProcessLineagePK.
        :type: list[SchemaLineageDependencyDef]
        """
        if data_flow is None:
            raise ValueError("Invalid value for `data_flow`, must not be `None`")

        self._data_flow = data_flow

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
        if not isinstance(other, ProcessLineagePK):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """
        Returns true if both objects are not equal
        """
        return not self == other
