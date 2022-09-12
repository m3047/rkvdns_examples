#!/usr/bin/python3
# Copyright (c) 2022 by Fred Morris Tacoma WA
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
from time import strftime, gmtime

import totalizer.agent_utils as agent_utils

class TestWatchRule(unittest.TestCase):
    """Tests for the rule parser."""
    
    def setUp(self):
        self.rules = agent_utils.WatchList()
        self.rules.define(address='1.1.1.1', port=3047, foo='Foo', bar='BAAAR', matchex='x', ttl=1)
        return
    
    def test_basic_good(self):
        """Basic test which should succeed."""
        self.rules.rule(keypattern='<foo>;<bar>')
        self.assertEqual(self.rules.rules[0].key(), 'Foo;BAAAR')
        return
    
    def test_basic_bad_kp(self):
        """Basic test bad keypattern."""
        with self.assertRaises(agent_utils.ParseError):
            self.rules.rule(keypattern='<foo>;<<bar>')
        with self.assertRaises(agent_utils.ParseError):
            self.rules.rule(keypattern='<{foo}>;<bar>')
        with self.assertRaises(agent_utils.ParseError):
            self.rules.rule(keypattern='{foo};<bar>')
        return
    
    def test_optional_bad(self):
        """Optional element bad."""
        with self.assertRaises(agent_utils.ParseError):
            self.rules.rule(keypattern='<foo>;<bar>{;baz}')
        return

    def test_nonoptional_missing(self):
        """Required element missing."""
        self.rules.rule(keypattern='<foo>;<bar>;<baz>')
        with self.assertRaises(KeyError):
            self.rules.rules[0].key()
        return

    def test_optional_missing(self):
        """Optional element missing."""
        self.rules.rule(keypattern='<foo>;<bar>{;<baz>}')
        self.assertEqual(self.rules.rules[0].key(), 'Foo;BAAAR')
        return
    
    def test_optional_present(self):
        """Optional element present."""
        self.rules.rule(keypattern='<foo>;<bar>{;<baz>}')
        self.assertEqual(self.rules.rules[0].key(baz='soup'), 'Foo;BAAAR;soup')
        return

    def test_timestamp(self):
        """With a generated timestamp."""
        self.rules.define(start_ts=None)
        self.rules.rule(keypattern='<foo>;<bar>;<start_ts>')
        self.assertEqual(self.rules.rules[0].key(),
                        'Foo;BAAAR;{}'.format(strftime( agent_utils.TS_FORMAT, gmtime(self.rules.rules[0].start_ts)))
                        )
        return
        

if __name__ == '__main__':
    unittest.main(verbosity=2)
