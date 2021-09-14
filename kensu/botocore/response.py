import botocore.response as btr

class ksu_bytes(bytes):
    ksu_metadata = {}

    @property
    def __class__(self):
        return bytes


class StreamingBody(btr.StreamingBody):
    ksu_metadata = {}

    def read(self, amt=None):
        result = super(StreamingBody, self).read(amt)
        if isinstance(result, bytes):
            result = ksu_bytes(result)
            result.ksu_metadata = self.ksu_metadata
        return result