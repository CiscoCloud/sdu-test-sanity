
# Copyright (c) 2010-2013 Yahoo! Inc. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License. See accompanying LICENSE file.

import re
import operator


def block_to_list(block):
    """ Convert a range block into a numeric list
        input "1-3,17,19-20"
        output=[1,2,3,17,19,20]
    """
    block += ','
    result = []
    val = val1 = ''
    in_range = False
    for letter in block:
        if letter in [',', '-']:
            if in_range:
                val2 = val
                val2_len = len(val2)
                # result+=range(int(val1),int(val2)+1)
                for value in range(int(val1), int(val2) + 1):
                    if val1.startswith('0'):
                        result.append(str(value).zfill(val2_len))
                    else:
                        result.append(str(value))
                val = ''
                val1 = None
                in_range = False
            else:
                val1 = val
                val1_len = len(val1)
                val = ''
            if letter == ',':
                if val1 is not None:
                    result.append(val1.zfill(val1_len))  # pragma: no cover
            else:
                in_range = True
        else:
            val += letter
    return result


def expand_item1(item):
    result = []
    in_block = False
    pre_block = ''
    for count in range(0, len(item)):
        letter = item[count]
        if letter == '[':
            in_block = True
            block = ''
        elif letter == ']' and in_block:
            in_block = False
            for value in block_to_list(block):
                result.append('%s%s%s' % (pre_block, value, item[count + 1:]))
        elif in_block:
            block += letter
        elif not in_block:
            pre_block += letter
    if len(result):
        return result
    else:
        return [item]  # pragma: no cover


def expand_item(range_list, onepass=False):
    """ Expand a list of plugin:parameters into a list of hosts """

    if isinstance(range_list, str):
        range_list = [range_list]

    # Iterate through our list
    newlist = []
    found_plugin = False
    for item in range_list:
        # Is the item a plugin
        temp = item.split(':')
        newlist += expand_item1(temp[0])
    # by another plugin.  For example a dns resource that has an address that
    # points to a load balancer vip that may container a number of hosts that
    # need to be looked up via the load_balancer plugin.
    if found_plugin and not onepass:
        newlist = expand_item(newlist)
    return newlist


def expand(range_list, onepass=False):
    """
    Expand a list of lists and set operators into a final host lists
    >>> host_lists.expand(['foo[01-10]','-','foo[04-06]'])
    ['foo09', 'foo08', 'foo07', 'foo02', 'foo01', 'foo03', 'foo10']
    >>>
    """
    if isinstance(range_list, str):  # pragma: no cover
        range_list = [h.strip() for h in range_list.split(',')]
    new_list = []
    set1 = None
    operation = None
    for item in range_list:
        if set1 and operation:
            set2 = expand_item(item)
            new_list.append(list(set(set1).difference(set(set2))))
            set1 = None
            operation = None
        elif item in ['-'] and len(new_list):
            set1 = new_list.pop()
            operation = item
        else:
            expanded_item = expand_item(item, onepass=onepass)
            new_list.append(expanded_item)
    new_list2 = []
    for item in new_list:
        new_list2 += item
    return new_list2


def cmp_compat(a, b):
    """
    Simple comparison function
    :param a:
    :param b:
    :return:
    """
    return (a > b) - (a < b)


def multikeysort(items, columns):
    comparers = [
        ((operator.itemgetter(col[1:].strip()), -1)
         if col.startswith('-') else (operator.itemgetter(col.strip()), 1))
        for col in columns
    ]

    def comparer(left, right):
        for fn, mult in comparers:
            try:
                result = cmp_compat(fn(left), fn(right))
            except KeyError:
                return 0
            if result:
                return mult * result
        else:
            return 0
    try:
        # noinspection PyArgumentList
        return sorted(items, cmp=comparer)
    except TypeError:
        # Python 3 removed the cmp parameter
        import functools
        return sorted(items, key=functools.cmp_to_key(comparer))


def compress(hostnames):
    """
    Compress a list of host into a more compact range representation
    """
    domain_dict = {}
    result = []
    for host in hostnames:
        if '.' in host:
            domain = '.'.join(host.split('.')[1:])
        else:
            domain = ''
        try:
            domain_dict[domain].append(host)
        except KeyError:
            domain_dict[domain] = [host]
    domains = list(domain_dict.keys())
    domains.sort()
    for domain in domains:
        hosts = compress_domain(domain_dict[domain])
        result += hosts
    return result


def compress_domain(hostnames):
    """
    Compress a list of hosts in a domain into a more compact representation
    """
    hostnames.sort()
    prev_dict = {'prefix': "", 'suffix': '', 'number': 0}
    items = []
    items_block = []
    new_hosts = []
    for host in hostnames:
        try:
            parsed_dict = (re.match(
                r"(?P<prefix>.*?)(?P<number>\d+)?(?P<suffix>[^\d]*[.].*).?",
                host)
            ).groupdict()
            # To generate the range we need the entries sorted numerically
            # but to ensure we don't loose any leading 0s we don't want to
            # replace the number parameter that is a string with the leading
            # 0s.
            parsed_dict['number_int'] = int(parsed_dict['number'])
            new_hosts.append(parsed_dict)
        except AttributeError:
            if '.' not in host:
                host += '.'
                parsed_dict = {'host': compress([host])[0].strip('.')}
            else:
                parsed_dict = {'host': host}
            new_hosts.append(parsed_dict)
    new_hosts = multikeysort(new_hosts, ['prefix', 'number_int'])
    for parsed_dict in new_hosts:
        if 'host' in parsed_dict.keys() or \
                parsed_dict['prefix'] != prev_dict['prefix'] or \
                parsed_dict['suffix'] != prev_dict['suffix'] or \
                int(parsed_dict['number']) != int(prev_dict['number']) + 1:
            if len(items_block):
                items.append(items_block)
            items_block = [parsed_dict]
        else:
            items_block.append(parsed_dict)
        prev_dict = parsed_dict
    items.append(items_block)
    result = []
    for item in items:
        if len(item):
            if len(item) == 1 and 'host' in item[0].keys():
                result.append(item[0]['host'])
            elif len(item) == 1:
                result.append(
                    '%s%s%s' % (
                        item[0]['prefix'], item[0]['number'], item[0]['suffix']
                    )
                )
            else:
                result.append(
                    '%s[%s-%s]%s' % (
                        item[0]['prefix'],
                        item[0]['number'],
                        item[-1]['number'],
                        item[0]['suffix']
                    )
                )
    return result
