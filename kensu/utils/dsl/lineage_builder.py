from kensu.utils.dsl.process_lineage_deps_builder import ProcessLineageDepsBuilder


class LineageBuilder(object):
  def __init__(self, kensu, report_stats):
    self.kensu = kensu
    self.deps = []
    self.report_stats = report_stats

  @property
  def n(self):
    return self.new_dependency()
  def new_dependency(self):
    return ProcessLineageDepsBuilder(self.kensu, self)
  def add_deps(self, dep):
    self.deps.append(dep)

  def e(self, **kwargs):
    return self.end_lineage(**kwargs)
  def end_lineage(self, **kwargs):
    self.kensu.new_lineage(self.deps, self.report_stats, **kwargs)
