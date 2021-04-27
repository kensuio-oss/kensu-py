from hashlib import sha1

class SimpleCache(object):
  def __init__(self):
    self.CACHE = {}
  def hash(self, o):
    return sha1(str(o).encode()).hexdigest()
  def put(self, k, o):
    kh = self.hash(k)
    self.CACHE[kh] = o
  def contains(self, o):
    k = self.hash(o)
    return k in self.CACHE
  def get(self, o):
    if self.contains(o):
      k = self.hash(o)
      return self.CACHE[k]
    else:
      return None