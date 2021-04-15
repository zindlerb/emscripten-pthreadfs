# Copyright 2032 The Emscripten Authors.  All rights reserved.
# Emscripten is available under two separate licenses, the MIT license and the
# University of Illinois/NCSA Open Source License.  Both these licenses can be
# found in the LICENSE file.

import difflib
import json
import os
import re

from .utils import path_from_root, exit_with_error
from . import diagnostics


class _impl:
  attrs = {}
  internal_settings = set()

  def __init__(self):
    self.reset()

  @classmethod
  def reset(cls):
    cls.attrs = {}

    # Load the JS defaults into python.
    settings = open(path_from_root('src', 'settings.js')).read().replace('//', '#')
    settings = re.sub(r'var ([\w\d]+)', r'attrs["\1"]', settings)
    # Variable TARGET_NOT_SUPPORTED is referenced by value settings.js (also beyond declaring it),
    # so must pass it there explicitly.
    exec(settings, {'attrs': cls.attrs})

    settings = open(path_from_root('src', 'settings_internal.js')).read().replace('//', '#')
    settings = re.sub(r'var ([\w\d]+)', r'attrs["\1"]', settings)
    internal_attrs = {}
    exec(settings, {'attrs': internal_attrs})
    cls.attrs.update(internal_attrs)

    if 'EMCC_STRICT' in os.environ:
      cls.attrs['STRICT'] = int(os.environ.get('EMCC_STRICT'))

    # Special handling for LEGACY_SETTINGS.  See src/setting.js for more
    # details
    cls.legacy_settings = {}
    cls.alt_names = {}
    for legacy in cls.attrs['LEGACY_SETTINGS']:
      if len(legacy) == 2:
        name, new_name = legacy
        cls.legacy_settings[name] = (None, 'setting renamed to ' + new_name)
        cls.alt_names[name] = new_name
        cls.alt_names[new_name] = name
        default_value = cls.attrs[new_name]
      else:
        name, fixed_values, err = legacy
        cls.legacy_settings[name] = (fixed_values, err)
        default_value = fixed_values[0]
      assert name not in cls.attrs, 'legacy setting (%s) cannot also be a regular setting' % name
      if not cls.attrs['STRICT']:
        cls.attrs[name] = default_value

    cls.internal_settings = set(internal_attrs.keys())

  # Transforms the Settings information into emcc-compatible args (-s X=Y, etc.). Basically
  # the reverse of load_settings, except for -Ox which is relevant there but not here
  @classmethod
  def serialize(cls):
    ret = []
    for key, value in cls.attrs.items():
      if key == key.upper():  # this is a hack. all of our settings are ALL_CAPS, python internals are not
        jsoned = json.dumps(value, sort_keys=True)
        ret += ['-s', key + '=' + jsoned]
    return ret

  @classmethod
  def to_dict(cls):
    return cls.attrs.copy()

  @classmethod
  def copy(cls, values):
    cls.attrs = values

  @classmethod
  def apply_opt_level(cls, opt_level, shrink_level=0, noisy=False):
    if opt_level >= 1:
      cls.attrs['ASSERTIONS'] = 0
    if shrink_level >= 2:
      cls.attrs['EVAL_CTORS'] = 1

  def keys(self):
    return self.attrs.keys()

  def __getattr__(self, attr):
    if attr in self.attrs:
      return self.attrs[attr]
    else:
      raise AttributeError("Settings object has no attribute '%s'" % attr)

  def __setattr__(self, attr, value):
    if attr == 'STRICT' and value:
      for a in self.legacy_settings:
        self.attrs.pop(a, None)

    if attr in self.legacy_settings:
      # TODO(sbc): Rather then special case this we should have STRICT turn on the
      # legacy-settings warning below
      if self.attrs['STRICT']:
        exit_with_error('legacy setting used in strict mode: %s', attr)
      fixed_values, error_message = self.legacy_settings[attr]
      if fixed_values and value not in fixed_values:
        exit_with_error('Invalid command line option -s ' + attr + '=' + str(value) + ': ' + error_message)
      diagnostics.warning('legacy-settings', 'use of legacy setting: %s (%s)', attr, error_message)

    if attr in self.alt_names:
      alt_name = self.alt_names[attr]
      self.attrs[alt_name] = value

    if attr not in self.attrs:
      msg = "Attempt to set a non-existent setting: '%s'\n" % attr
      suggestions = difflib.get_close_matches(attr, list(self.attrs.keys()))
      suggestions = [s for s in suggestions if s not in self.legacy_settings]
      suggestions = ', '.join(suggestions)
      if suggestions:
        msg += ' - did you mean one of %s?\n' % suggestions
      msg += " - perhaps a typo in emcc's  -s X=Y  notation?\n"
      msg += ' - (see src/settings.js for valid values)'
      exit_with_error(msg)

    self.attrs[attr] = value

  @classmethod
  def get(cls, key):
    return cls.attrs.get(key)

  @classmethod
  def __getitem__(cls, key):
    return cls.attrs[key]

  @classmethod
  def target_environment_may_be(self, environment):
    return self.attrs['ENVIRONMENT'] == '' or environment in self.attrs['ENVIRONMENT'].split(',')

# Settings. A global singleton. Not pretty, but nicer than passing |, settings| everywhere
class SettingsManager:

  __instance = None

  @staticmethod
  def instance():
    if SettingsManager.__instance is None:
      SettingsManager.__instance = _impl()
    return SettingsManager.__instance

  def __getattr__(self, attr):
    return getattr(self.instance(), attr)

  def __setattr__(self, attr, value):
    return setattr(self.instance(), attr, value)

  def get(self, key):
    return self.instance().get(key)

  def __getitem__(self, key):
    return self.instance()[key]
