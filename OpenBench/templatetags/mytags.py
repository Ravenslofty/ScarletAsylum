# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                             #
#   OpenBench is a chess engine testing framework authored by Andrew Grant.   #
#   <https://github.com/AndyGrant/OpenBench>           <andrew@grantnet.us>   #
#                                                                             #
#   OpenBench is free software: you can redistribute it and/or modify         #
#   it under the terms of the GNU General Public License as published by      #
#   the Free Software Foundation, either version 3 of the License, or         #
#   (at your option) any later version.                                       #
#                                                                             #
#   OpenBench is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#   GNU General Public License for more details.                              #
#                                                                             #
#   You should have received a copy of the GNU General Public License         #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

import django
import html
import json
import re

from django.utils.safestring import mark_safe

import OpenBench.config
import OpenBench.models
import OpenBench.spsa_utils
import OpenBench.stats
import OpenBench.utils

def oneDigitPrecision(value):
    try:
        value = round(value, 1)
        if '.' not in str(value):
            return str(value) + '.0'
        pre, post = str(value).split('.')
        post += '0'
        return pre + '.' + post[0:1]
    except:
        return value

def twoDigitPrecision(value):
    try:
        value = round(value, 2)
        if '.' not in str(value):
            return str(value) + '.00'
        pre, post = str(value).split('.')
        post += '00'
        return pre + '.' + post[0:2]
    except:
        return value

def gitDiffLink(test):

    engines = OpenBench.config.OPENBENCH_CONFIG['engines']

    if test.dev_engine in engines and engines[test.dev_engine]['private']:
        repo = OpenBench.config.OPENBENCH_CONFIG['engines'][test.dev_engine]['source']
    else:
        repo = OpenBench.utils.path_join(*test.dev.source.split('/')[:-2])

    if test.test_mode == 'SPSA':
        return OpenBench.utils.path_join(repo, 'compare', test.dev.sha[:8])

    return OpenBench.utils.path_join(repo, 'compare',
        '{0}..{1}'.format( test.base.sha[:8], test.dev.sha[:8]))

def shortStatBlock(test):

    tri_line   = 'Games: %d W: %d L: %d D: %d' % test.as_nwld()
    penta_line = 'Ptnml(0-2): %d, %d, %d, %d, %d' % test.as_penta()

    if test.test_mode == 'SPSA':
        spsa_run = test.spsa_run # Avoid extra database accesses
        statlines = [
            'Tuning %d Parameters' % (spsa_run.parameters.count()),
            '%d/%d Iterations' % (test.games / (2 * spsa_run.pairs_per), spsa_run.iterations),
            '%d/%d Games Played' % (test.games, 2 * spsa_run.iterations * spsa_run.pairs_per)]

    elif test.test_mode == 'SPRT':
        llr_line = 'LLR: %0.2f (%0.2f, %0.2f) [%0.2f, %0.2f]' % (
            test.currentllr, test.lowerllr, test.upperllr, test.elolower, test.eloupper)
        statlines = [llr_line, tri_line, penta_line] if test.use_penta else [llr_line, tri_line]

    elif test.test_mode == 'GAMES':
        lower, elo, upper = OpenBench.stats.Elo(test.results())
        elo_line = 'Elo: %0.2f +- %0.2f (95%%) [N=%d]' % (elo, max(upper - elo, elo - lower), test.max_games)
        statlines = [elo_line, tri_line, penta_line] if test.use_penta else [elo_line, tri_line]

    elif test.test_mode == 'DATAGEN':
        status_line = 'Generated %d/%d Games' % (test.games, test.max_games)
        lower, elo, upper = OpenBench.stats.Elo(test.results())
        elo_line = 'Elo: %0.2f +- %0.2f (95%%) [N=%d]' % (elo, max(upper - elo, elo - lower), test.max_games)
        statlines = [status_line, elo_line, penta_line] if test.use_penta else [status_line, elo_line, tri_line]

    return '\n'.join(statlines)

def longStatBlock(test):

    assert test.test_mode != 'SPSA'

    threads     = int(OpenBench.utils.extract_option(test.dev_options, 'Threads'))
    hashmb      = int(OpenBench.utils.extract_option(test.dev_options, 'Hash'))
    timecontrol = test.dev_time_control + ['s', '']['=' in test.dev_time_control]
    type_text   = 'SPRT' if test.test_mode == 'SPRT' else 'Conf'

    lower, elo, upper = OpenBench.stats.Elo(test.results())

    lines = [
        'Elo   | %0.2f +- %0.2f (95%%)' % (elo, max(upper - elo, elo - lower)),
        '%-5s | %s Threads=%d Hash=%dMB' % (type_text, timecontrol, threads, hashmb),
    ]

    if test.test_mode == 'SPRT':
        lines.append('LLR   | %0.2f (%0.2f, %0.2f) [%0.2f, %0.2f]' % (
            test.currentllr, test.lowerllr, test.upperllr, test.elolower, test.eloupper))

    lines.append('Games | N: %d W: %d L: %d D: %d' % test.as_nwld())

    if test.use_penta:
        lines.append('Penta | [%d, %d, %d, %d, %d]' % test.as_penta())

    return '\n'.join(lines)

def testResultColour(test):

    if test.passed:
        if test.elolower + test.eloupper < 0: return 'blue'
        return 'green'
    if test.failed:
        if test.wins >= test.losses: return 'yellow'
        return 'red'
    return ''

def sumAttributes(iterable, attribute):
    try: return sum([getattr(f, attribute) for f in iterable])
    except: return 0

def insertCommas(value):
    return '{:,}'.format(int(value))

def prettyName(name):
    if re.search('^[0-9a-fA-F]{40}$', name):
        return name[:16].upper()
    return name

def prettyDevName(test):

    # If engines are different, use the base name + branch
    if test.dev_engine != test.base_engine:
        return '[%s] %s' % (test.base_engine, test.base.name)

    # If testing different Networks, possibly use the Network name
    if test.dev.name == test.base.name and test.dev_netname != '':

        # Nets match as well, so revert back to the branch name
        if test.dev_network == test.base_network:
            return prettyName(test.dev.name)

        # Use the network's name, if we still have it saved
        try: return OpenBench.models.Network.objects.get(sha256=test.dev_network).name
        except: return test.dev_netname # File has since been deleted ?

    return prettyName(test.dev.name)

def testIdToPrettyName(test_id):
    return prettyName(OpenBench.models.Test.objects.get(id=test_id).dev.name)

def testIdToTimeControl(test_id):
    return OpenBench.models.Test.objects.get(id=test_id).dev_time_control

def cpuflagsBlock(machine, N=8):

    reported = []
    flags    = machine.info['cpu_flags']

    general_flags   = ['BMI2', 'POPCNT']
    broad_avx_flags = ['AVX2', 'AVX', 'SSE42', 'SSE41', 'SSSE3']

    for flag in general_flags:
        if flag in flags:
            reported.append(flag)
            break

    for flag in broad_avx_flags:
        if flag in flags:
            reported.append(flag)
            break

    for flag in flags:
        if flag not in general_flags and flag not in broad_avx_flags:
            reported.append(flag)

    return ' '.join(reported)

def compilerBlock(machine):
    string = ''
    for engine, info in machine.info['compilers'].items():
        string += '%-16s %-8s (%s)\n' % (engine, info[0], info[1])
    return string

def removePrefix(value, prefix):
    return value.removeprefix(prefix)

def machine_name(machine_id):
    try:
        machine = OpenBench.models.Machine.objects.get(id=machine_id)
        return machine.info['machine_name']
    except: return 'None'


def llr_history_graph(test, width=320, height=112):

    if test.test_mode != 'SPRT':
        return ''

    history = list(OpenBench.utils.load_llr_history(test))
    
    # Ensure graph starts at 0,0
    if not history or history[0][0] != 0:
        history.insert(0, [0, 0.0])

    # Ensure current point is the latest in history
    if history[-1][0] != test.games or history[-1][1] != test.currentllr:
        history.append([test.games, test.currentllr])

    x_max = max(max(p[0] for p in history), 1)

    # ──── Symmetry and Boundary Logic ────
    # We want 0.0 to be the dead-center. 
    # Find the largest absolute extent including current bounds and historical data.
    obs_max = max(abs(test.lowerllr), abs(test.upperllr), max(abs(p[1]) for p in history))
    
    # Add a minimum scale and some padding
    extent = max(obs_max * 1.15, 0.5)
    y_min, y_max = -extent, extent

    L, R, T, B = 8, 8, 8, 8
    iw = max(width  - L - R, 1)
    ih = max(height - T - B, 1)
    sx = lambda v: L + iw * (v / x_max)
    sy = lambda v: T + ih * (1.0 - (v - y_min) / (y_max - y_min))

    pts = [{'g': g, 'l': round(l, 4), 'x': round(sx(g), 2), 'y': round(sy(l), 2)}
           for g, l in history]

    def cross(a, b):
        denom = (b['l'] - a['l'])
        if abs(denom) < 1e-7: return None
        r = -a['l'] / denom
        return {'g': a['g'] + r * (b['g'] - a['g']), 'l': 0.0,
                'x': round(a['x'] + r * (b['x'] - a['x']), 2),
                'y': round(sy(0.0), 2)}

    pos_segs, neg_segs = [], []
    seg = [pts[0]]
    seg_pos = pts[0]['l'] >= 0.0
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        b_pos = b['l'] >= 0.0
        if b_pos == seg_pos:
            seg.append(b)
            continue
        c = cross(a, b)
        if c: seg.append(c)
        if len(seg) >= 2:
            (pos_segs if seg_pos else neg_segs).append(seg)
        seg = [c, b] if c else [b]
        seg_pos = b_pos
    if len(seg) >= 2:
        (pos_segs if seg_pos else neg_segs).append(seg)

    def polyline(cls, segments):
        return ''.join(
            '<polyline class="%s" points="%s"/>' %
            (cls, ' '.join('%.2f,%.2f' % (p['x'], p['y']) for p in s))
            for s in segments)

    y_mid = 0.0
    grid = []
    # Grid lines at top, center, bottom
    for v in (y_max, 0.0, y_min):
        y = sy(v)
        grid.append('<line class="llr-grid" x1="%d" y1="%.2f" x2="%d" y2="%.2f"/>'
                    % (L, y, width - R, y))
    # Time grid lines
    for v in (x_max / 4.0, x_max / 2.0, 3.0 * x_max / 4.0):
        x = sx(v)
        grid.append('<line class="llr-grid" x1="%.2f" y1="%d" x2="%.2f" y2="%d"/>'
                    % (x, T, x, height - B))

    guides = []
    for v, cls in ((test.lowerllr, 'llr-bound'), (0.0, 'llr-zero'), (test.upperllr, 'llr-bound')):
        y = sy(v)
        guides.append('<line class="%s" x1="%d" y1="%.2f" x2="%d" y2="%.2f"/>'
                        % (cls, L, y, width - R, y))

    last = pts[-1]
    title = 'LLR %.2f after %d games' % (test.currentllr, test.games)
    history_json = html.escape(json.dumps(pts, separators=(',', ':')))

    svg = (
        '<div class="llr-history-widget" data-history="%s">'
        '<div class="llr-history-chart">'
        '<div class="llr-history-yaxis"><div>%.2f</div><div>0.00</div><div>%.2f</div></div>'
        '<div class="llr-history-main">'
        '<div class="llr-history-plot">'
        '<svg class="llr-history-graph" viewBox="0 0 %d %d" width="%d" height="%d" '
        'role="img" aria-label="%s">'
        '<title>%s</title>'
        '<rect class="llr-bg" x="0" y="0" width="%d" height="%d" rx="5"/>'
        '%s%s%s%s'
        '<line class="llr-hover-line" x1="%.2f" y1="%d" x2="%.2f" y2="%d"/>'
        '<circle class="llr-hover-point" cx="%.2f" cy="%.2f" r="3"/>'
        '<rect class="llr-hitbox" x="0" y="0" width="%d" height="%d" rx="5"/>'
        '</svg>'
        '<div class="llr-history-tooltip"></div>'
        '</div>'
        '<div class="llr-history-xaxis"><div>0</div><div>%d</div><div>%d g</div></div>'
        '</div></div></div>'
    ) % (
        history_json,
        y_max, y_min,
        width, height, width, height,
        html.escape(title), html.escape(title),
        width, height,
        ''.join(grid), ''.join(guides),
        polyline('llr-path llr-path-pos', pos_segs),
        polyline('llr-path llr-path-neg', neg_segs),
        last['x'], T, last['x'], height - B,
        last['x'], last['y'],
        width, height,
        int(round(x_max / 2.0)), x_max,
    )
    return mark_safe(svg)


def spsa_history_graph(test, width=320, height=300):

    if test.test_mode != 'SPSA':
        return ''

    history = OpenBench.utils.get_spsa_history(test)
    if not history:
        return ''

    scaled = {
        name: [[g, v * 100.0] for g, v in series]
        for name, series in history.items()
        if series
    }

    all_values = [v for series in scaled.values() for _, v in series]
    if not all_values:
        return ''

    y_min, y_max = min(all_values), max(all_values)
    span = y_max - y_min
    pad = max(span * 0.10, 1.0)
    y_min, y_max = y_min - pad, y_max + pad

    x_max = max(max(pt[0] for series in scaled.values() for pt in series), 1)

    L, R, T, B = 8, 8, 8, 8
    iw = max(width - L - R, 1)
    ih = max(height - T - B, 1)

    sx = lambda x: L + iw * (x / x_max)
    sy = lambda y: T + ih * (1.0 - (y - y_min) / (y_max - y_min))

    colors = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]

    paths = []
    for idx, (name, series) in enumerate(scaled.items()):
        if len(series) < 2:
            continue

        pts_str = ' '.join('%.2f,%.2f' % (round(sx(g), 2), round(sy(v), 2)) for g, v in series)
        color = colors[idx % len(colors)]
        
        paths.append(
            '<polyline class="spsa-path" stroke="%s" points="%s"><title>%s</title></polyline>' % (color, pts_str, name)
        )

    y_mid = (y_min + y_max) / 2.0
    x_mid = x_max / 2.0

    grid = []
    for val in [y_max, y_mid, y_min]:
        y = sy(val)
        grid.append('<line class="spsa-grid" x1="%d" y1="%.2f" x2="%d" y2="%.2f"/>' % (L, y, width - R, y))

    x = sx(x_mid)
    grid.append('<line class="spsa-grid" x1="%.2f" y1="%d" x2="%.2f" y2="%d"/>' % (x, T, x, height - B))

    svg = (
        '<div class="spsa-history-widget">'
        '<div class="spsa-history-chart">'
        '<div class="spsa-history-yaxis"><div>%.1f%%</div><div>%.1f%%</div><div>%.1f%%</div></div>'
        '<div class="spsa-history-main">'
        '<div class="spsa-history-plot">'
        '<svg class="spsa-history-graph" viewBox="0 0 %d %d" width="%d" height="%d">'
        '<rect class="spsa-bg" x="0" y="0" width="%d" height="%d" rx="5"/>'
        '%s%s'
        '</svg>'
        '</div>'
        '<div class="spsa-history-xaxis"><div>0</div><div>%d</div><div>%d g</div></div>'
        '</div></div></div>'
    ) % (
        y_max, y_mid, y_min,
        width, height, width, height,
        width, height,
        ''.join(grid), ''.join(paths),
        int(round(x_max / 2.0)), int(x_max)
    )
    return mark_safe(svg)


register = django.template.Library()
register.filter('oneDigitPrecision', oneDigitPrecision)
register.filter('twoDigitPrecision', twoDigitPrecision)
register.filter('gitDiffLink', gitDiffLink)
register.filter('shortStatBlock', shortStatBlock)
register.filter('longStatBlock', longStatBlock)
register.filter('testResultColour', testResultColour)
register.filter('sumAttributes', sumAttributes)
register.filter('insertCommas', insertCommas)
register.filter('prettyName', prettyName)
register.filter('prettyDevName', prettyDevName)
register.filter('testIdToPrettyName', testIdToPrettyName)
register.filter('testIdToTimeControl', testIdToTimeControl)
register.filter('cpuflagsBlock', cpuflagsBlock)
register.filter('compilerBlock', compilerBlock)
register.filter('removePrefix', removePrefix)
register.filter('machine_name', machine_name)
register.filter('llr_history_graph', llr_history_graph)
register.filter('spsa_history_graph', spsa_history_graph)

def book_download_link(workload):
    if workload.book_name in OpenBench.config.OPENBENCH_CONFIG['books']:
        return OpenBench.config.OPENBENCH_CONFIG['books'][workload.book_name]['source']

def network_download_link(workload, branch):

    assert branch in [ 'dev', 'base' ]

    sha    = workload.dev_network if branch == 'dev' else workload.base_network
    engine = workload.dev_engine  if branch == 'dev' else workload.base_engine

    # Network could have been deleted after this workload was finished
    if (network := OpenBench.models.Network.objects.filter(sha256=sha, engine=engine).first()):
        return '/networks/%s/download/%s/' % (engine, sha)

    return '/networks/%s/' % (engine)

def workload_url(workload):

    # Might be a workload id
    if type(workload) == int:
        workload = OpenBench.models.Test.objects.get(id=workload)

    # Differentiate between Tunes, Datagen, and regular Tests
    mapping = { 'SPSA' : 'tune', 'DATAGEN' : 'datagen' }
    return '/%s/%d/' % (mapping.get(workload.test_mode, 'test'), workload.id)

def workload_pretty_name(workload):

    # Might be a workload id
    if type(workload) == int:
        workload = OpenBench.models.Test.objects.get(id=workload)

    # Convert commit sha's to just the first 16 characters
    if re.search('^[0-9a-fA-F]{40}$', workload.dev.name):
        return workload.dev.name[:16].lower()

    return workload.dev.name

def git_diff_text(workload, N=24):

    from django.utils.html import escape, mark_safe

    dev_name = workload.dev.name
    dev_name = dev_name[:N] + '...' if len(dev_name) > N else dev_name

    base_name = workload.base.name
    base_name = base_name[:N] + '...' if len(base_name) > N else base_name

    return mark_safe('%s <span class="diff-vs">vs</span> %s' % (escape(dev_name), escape(base_name)))


def test_is_smp_odds(test):
    dev_threads  = int(OpenBench.utils.extract_option(test.dev_options , 'Threads'))
    base_threads = int(OpenBench.utils.extract_option(test.base_options, 'Threads'))
    return dev_threads != base_threads

def test_is_time_odds(test):
    return test.dev_time_control != test.base_time_control

def test_is_fischer(test):
    return 'FRC' in test.book_name.upper() or '960' in test.book_name.upper()

register.filter('book_download_link', book_download_link)
register.filter('network_download_link', network_download_link)

register.filter('workload_url', workload_url)
register.filter('workload_pretty_name', workload_pretty_name)

register.filter('git_diff_text', git_diff_text)

register.filter('test_is_smp_odds'  , test_is_smp_odds  )
register.filter('test_is_time_odds' , test_is_time_odds )
register.filter('test_is_fischer'   , test_is_fischer   )


@register.filter
def next(iterable, index):
    try: return iterable[int(index) + 1]
    except: return None

@register.filter
def previous(iterable, index):
    try: return iterable[int(index) - 1]
    except: return None
