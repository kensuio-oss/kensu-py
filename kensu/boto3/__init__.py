import boto3

def kensu_put(self,**kwargs):
    self.put(**kwargs)
    print('This is my custom method'+str(kwargs))

def add_custom_method(class_attributes, **kwargs):
    class_attributes['kensu_put'] = kensu_put

boto3._get_default_session().events.register("creating-resource-class.s3.Object",
                        add_custom_method)
