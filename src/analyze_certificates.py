import operator
from graphviz import Digraph
from tabulate import tabulate
import matplotlib.pyplot as plt; plt.rcdefaults()
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.pyplot import figure
from dateutil import parser
import datetime
from tags_constants import *

STOP_ON_UNEXPECTED_NUMS = False


def is_in_dict(target_dict, path):
    current_level = target_dict
    for item in path:
        if item not in current_level:
            return False
        else:
            current_level = current_level[item]
    return True


def get_item_from_dict(target_dict, path):
    current_level = target_dict
    for item in path:
        if item not in current_level:
            return None
        else:
            current_level = current_level[item]
    return current_level


def plot_bar_graph(data, x_data_labels, y_label, title, file_name):
    fig_width = round(len(data) / 2)
    if fig_width < 10:
        fig_width = 10
    figure(num=None, figsize=(fig_width, 8), dpi=200, facecolor='w', edgecolor='k')
    y_pos = np.arange(len(x_data_labels))
    plt.bar(y_pos, data, align='center', alpha=0.5)
    plt.xticks(y_pos, x_data_labels)
    plt.xticks(rotation=45)
    plt.ylabel(y_label)
    plt.title(title)
    x1, x2, y1, y2 = plt.axis()
    plt.axis((x1, x2, y1 - 1, y2))
    plt.savefig(file_name + '.png', bbox_inches='tight')
    plt.savefig(file_name + '.pdf', bbox_inches='tight')


def plot_heatmap_graph(data_matrix, x_data_ticks, y_data_ticks, x_label, y_label, title, file_name):
    plt.figure(figsize=(round(len(x_data_ticks) / 2), 8), dpi=200, facecolor='w', edgecolor='k')
    #color_map = 'BuGn'
    color_map = 'Purples'
    plt.imshow(data_matrix, cmap=color_map, interpolation='none', aspect='auto')
    #sns.heatmap(data_matrix, cmap=color_map, linewidth=0.5)
    x_pos = np.arange(len(y_data_ticks))
    plt.yticks(x_pos, y_data_ticks)
    y_pos = np.arange(len(x_data_ticks))
    plt.xticks(y_pos, x_data_ticks)
    plt.xticks(rotation=90, ha='center')
    plt.gca().invert_yaxis()
    x1, x2, y1, y2 = plt.axis()
    plt.axis((x1, x2, y1 - 0.5, y2))
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    plt.title(title)
    plt.savefig(file_name + '.png', bbox_inches='tight')
    plt.savefig(file_name + '.pdf', bbox_inches='tight')


def compute_and_plot_hist(data, bins, y_label, title, file_name):
    hist_refs = np.histogram(data, bins)
    hist_labels = []
    for index in range(0, len(bins) - 1):
        if bins[index] == bins[index + 1] - 1:
            hist_labels.append('{}'.format(bins[index]))
        else:
            hist_labels.append('{}-{}'.format(bins[index], bins[index + 1]))
    # plot bar graph with number of certificates referenced by given number of other certificates
    plot_bar_graph(hist_refs[0], hist_labels, y_label, title, file_name)



def depricated_print_dot_graph_keywordsonly(filter_rules_group, all_items_found, cert_id, walk_dir, out_dot_name, thick_as_occurences):
    # print dot
    dot = Digraph(comment='Certificate ecosystem: {}'.format(filter_rules_group))
    dot.attr('graph', label='{}'.format(walk_dir), labelloc='t', fontsize='30')
    dot.attr('node', style='filled')

    # insert nodes believed to be cert id for the processed certificates
    for cert in cert_id.keys():
        if cert != "":
            dot.attr('node', color='green')
            dot.node(cert_id[cert])

    dot.attr('node', color='gray')
    for file_name in all_items_found.keys():
        just_file_name = file_name
        this_cert_id = cert_id[file_name]

        if file_name.rfind('\\') != -1:
            just_file_name = file_name[file_name.rfind('\\') + 1:]

        # insert file name and identified probable certification id
        if this_cert_id != "":
            dot.edge(this_cert_id, this_cert_id, label=just_file_name)

        items_found_group = all_items_found[file_name]
        for rules_group in items_found_group.keys():

            # process only specified rule groups
            if rules_group not in filter_rules_group:
                continue

            items_found = items_found_group[rules_group]
            for rule in items_found.keys():
                for match in items_found[rule]:
                    if match != this_cert_id:
                        if thick_as_occurences:
                            num_occurrences = str(items_found[rule][match][TAG_MATCH_COUNTER] / 3 + 1)
                        else:
                            num_occurrences = '1'
                        label = str(items_found[rule][match][TAG_MATCH_COUNTER]) # label with number of occurrences
                        if this_cert_id != "":
                            dot.edge(this_cert_id, match, color='orange', style='solid', label=label, penwidth=num_occurrences)

    # Generate dot graph using GraphViz into pdf
    dot.render(out_dot_name, view=False)
    print('{} pdf rendered'.format(out_dot_name))


def print_dot_graph(filter_rules_group, all_items_found, walk_dir, out_dot_name, thick_as_occurences):
    # print dot
    dot = Digraph(comment='Certificate ecosystem: {}'.format(filter_rules_group))
    dot.attr('graph', label='{}'.format(walk_dir), labelloc='t', fontsize='30')
    dot.attr('node', style='filled')

    # insert nodes believed to be cert id for the processed certificates
    for cert_long_id in all_items_found.keys():
        if is_in_dict(all_items_found[cert_long_id], ['processed', 'cert_id']):
            dot.attr('node', color='green')  # URL='https://www.commoncriteriaportal.org/' doesn't work for pdf
            dot.node(all_items_found[cert_long_id]['processed']['cert_id'])

    dot.attr('node', color='gray')
    for cert_long_id in all_items_found.keys():
        # do not continue if no keywords were extracted
        if 'keywords_scan' not in all_items_found[cert_long_id].keys():
            continue

        cert = all_items_found[cert_long_id]
        this_cert_id = ''
        if is_in_dict(cert, ['processed', 'cert_id']):
            this_cert_id = cert['processed']['cert_id']
        if is_in_dict(cert, ['csv_scan', 'cert_item_name']):
            this_cert_name = cert['csv_scan']['cert_item_name']

        just_file_name = cert['csv_scan']['link_cert_report_file_name']

        # insert file name and identified probable certification id
        if this_cert_id != "":
            dot.edge(this_cert_id, this_cert_id, label=just_file_name)

        items_found_group = all_items_found[cert_long_id]['keywords_scan']
        for rules_group in items_found_group.keys():

            # process only specified rule groups
            if rules_group not in filter_rules_group:
                continue

            items_found = items_found_group[rules_group]
            for rule in items_found.keys():
                for match in items_found[rule]:
                    if match != this_cert_id:
                        if thick_as_occurences:
                            num_occurrences = str(items_found[rule][match][TAG_MATCH_COUNTER] / 3 + 1)
                        else:
                            num_occurrences = '1'
                        label = str(items_found[rule][match][TAG_MATCH_COUNTER]) # label with number of occurrences
                        if this_cert_id != "":
                            dot.edge(this_cert_id, match, color='orange', style='solid', label=label, penwidth=num_occurrences)

    # Generate dot graph using GraphViz into pdf
    dot.render(out_dot_name, view=False)
    print('{} pdf rendered'.format(out_dot_name))


def plot_certid_to_item_graph(item_path, all_items_found, walk_dir, out_dot_name, thick_as_occurences):
    # print dot
    dot = Digraph(comment='Certificate ecosystem: {}'.format(item_path))
    dot.attr('graph', label='{}'.format(walk_dir), labelloc='t', fontsize='30')
    dot.attr('node', style='filled')

    # insert nodes believed to be cert id for the processed certificates
    for cert_long_id in all_items_found.keys():
        if is_in_dict(all_items_found[cert_long_id], ['processed', 'cert_id']):
            dot.attr('node', color='green')  # URL='https://www.commoncriteriaportal.org/' doesn't work for pdf
            dot.node(all_items_found[cert_long_id]['processed']['cert_id'])

    dot.attr('node', color='gray')
    for cert_long_id in all_items_found.keys():
        # do not continue if no values with specified path were extracted
        if item_path[0] not in all_items_found[cert_long_id].keys():
            continue

        cert = all_items_found[cert_long_id]
        this_cert_id = ''
        if is_in_dict(cert, ['processed', 'cert_id']):
            this_cert_id = cert['processed']['cert_id']

        if is_in_dict(cert, [item_path[0], item_path[1]]):
            items_found = cert[item_path[0]][item_path[1]]
            for rule in items_found:
                for match in items_found[rule]:
                    if match != this_cert_id:
                        if thick_as_occurences:
                            num_occurrences = str(items_found[rule][match][TAG_MATCH_COUNTER] / 3 + 1)
                        else:
                            num_occurrences = '1'
                        label = str(items_found[rule][match][TAG_MATCH_COUNTER]) # label with number of occurrences
                        if this_cert_id != "":
                            dot.edge(this_cert_id, match, color='orange', style='solid', label=label, penwidth=num_occurrences)

    # Generate dot graph using GraphViz into pdf
    dot.render(out_dot_name, view=False)
    print('{} pdf rendered'.format(out_dot_name))

def analyze_references_graph(filter_rules_group, all_items_found):
    # build cert_id to item name mapping
    certid_info = {}
    for cert_long_id in all_items_found.keys():
        cert = all_items_found[cert_long_id]
        if is_in_dict(cert, ['processed', 'cert_id']):
            if is_in_dict(cert, ['frontpage_scan', 'cert_item']):
                this_cert_id = cert['processed']['cert_id']
                if this_cert_id not in certid_info.keys():
                    certid_info[this_cert_id] = {}
                certid_info[this_cert_id]['cert_item'] = cert['frontpage_scan']['cert_item']

    # build list of references
    referenced_by = {}
    for cert_long_id in all_items_found.keys():
        # do not continue if no keywords were extracted ()
        if 'keywords_scan' not in all_items_found[cert_long_id].keys():
            continue

        cert = all_items_found[cert_long_id]
        this_cert_id = ''
        if is_in_dict(cert, ['processed', 'cert_id']):
            this_cert_id = cert['processed']['cert_id']

        items_found_group = all_items_found[cert_long_id]['keywords_scan']
        for rules_group in items_found_group.keys():

            # process only specified rule groups
            if rules_group not in filter_rules_group:
                continue

            items_found = items_found_group[rules_group]
            for rule in items_found.keys():
                for match in items_found[rule]:
                    if match != this_cert_id:
                        if this_cert_id != "":
                            # add this_cert_id to the list of references of match item
                            if match not in referenced_by:
                                referenced_by[match] = []
                            if this_cert_id not in referenced_by[match]:
                                referenced_by[match].append(this_cert_id)

    #
    # process direct references
    #
    referenced_by_direct_nums = {}
    for cert_id in referenced_by.keys():
        referenced_by_direct_nums[cert_id] = len(referenced_by[cert_id])

    print('### Certificates sorted by number of other certificates directly referencing them:')
    sorted_ref_direct = sorted(referenced_by_direct_nums.items(), key=operator.itemgetter(1), reverse=False)
    direct_refs = []
    for cert_id in sorted_ref_direct:
        direct_refs.append(cert_id[1])
        if is_in_dict(certid_info, [cert_id[0], 'cert_item']):
            print('  {} : {}x directly: {}'.format(cert_id[0], cert_id[1], certid_info[cert_id[0]]['cert_item']))
        else:
            print('  {} : {}x directly'.format(cert_id[0], cert_id[1]))
    print('  Total number of certificates referenced at least once: {}'.format(len(sorted_ref_direct)))

    step = 5
    max_refs = max(direct_refs) + step
    bins = [1, 2, 3, 4, 5] + list(range(6, max_refs + 1, step))
    compute_and_plot_hist(direct_refs, bins, 'Number of certificates', '# certificates with specific number of direct references', 'cert_direct_refs_frequency.png')


    EXPECTED_CERTS_REFERENCED_ONCE = 942
    if EXPECTED_CERTS_REFERENCED_ONCE != len(sorted_ref_direct):
        print('  ERROR: Different than expected num certificates referenced at least once: {} vs. {}'.format(EXPECTED_CERTS_REFERENCED_ONCE, len(sorted_ref_direct)))
        if STOP_ON_UNEXPECTED_NUMS:
            raise ValueError('ERROR: Stopping on unexpected intermediate numbers')

    #
    # compute indirect num of references
    #
    referenced_by_indirect = {}
    for cert_id in referenced_by.keys():
        referenced_by_indirect[cert_id] = set()
        for item in referenced_by[cert_id]:
            referenced_by_indirect[cert_id].add(item)

    new_change_detected = True
    while new_change_detected:
        new_change_detected = False

        certids_list = referenced_by.keys()
        for cert_id in certids_list:
            tmp_referenced_by_indirect_nums = referenced_by_indirect[cert_id].copy()
            for referencing in tmp_referenced_by_indirect_nums:
                if referencing in referenced_by.keys():
                    tmp_referencing = referenced_by_indirect[referencing].copy()
                    for in_referencing in tmp_referencing:
                        if in_referencing not in referenced_by_indirect[cert_id]:
                            new_change_detected = True
                            referenced_by_indirect[cert_id].add(in_referencing)

    print('### Certificates sorted by number of other certificates indirectly referencing them:')
    referenced_by_indirect_nums = {}
    for cert_id in referenced_by_indirect.keys():
        referenced_by_indirect_nums[cert_id] = len(referenced_by_indirect[cert_id])

    sorted_ref_indirect = sorted(referenced_by_indirect_nums.items(), key=operator.itemgetter(1), reverse=False)
    indirect_refs = []
    for cert_id in sorted_ref_indirect:
        indirect_refs.append(cert_id[1])
        if is_in_dict(certid_info, [cert_id[0], 'cert_item']):
            print('  {} : {}x indirectly: {}'.format(cert_id[0], cert_id[1], certid_info[cert_id[0]]['cert_item']))
        else:
            print('  {} : {}x indirectly'.format(cert_id[0], cert_id[1]))

    step = 5
    max_refs = max(indirect_refs) + step
    bins = [1, 2, 3, 4, 5] + list(range(6, max_refs + 1, step))
    compute_and_plot_hist(indirect_refs, bins, 'Number of certificates', '# certificates with specific number of indirect references', 'cert_indirect_refs_frequency.png')


def plot_schemes_multi_line_graph(x_ticks, data, prominent_data, x_label, y_label, title, file_name):

    figure(num=None, figsize=(16, 8), dpi=200, facecolor='w', edgecolor='k')

    line_types = ['-', ':', '-.', '--']
    num_lines_plotted = 0
    data_sorted = sorted(data.keys())
    for group in data_sorted:
        items_in_year = []
        for item in sorted(data[group]):
            num = len(data[group][item])
            items_in_year.append(num)

        if group in prominent_data:
            plt.plot(x_ticks, items_in_year, line_types[num_lines_plotted % len(line_types)], label=group, linewidth=3)
        else:
            # plot minor suppliers dashed
            plt.plot(x_ticks, items_in_year, line_types[num_lines_plotted % len(line_types)], label=group, linewidth=2)

        # change line type to prevent color repetitions
        num_lines_plotted += 1

    plt.rcParams.update({'font.size': 16})
    plt.legend(loc=2)
    plt.xticks(x_ticks, rotation=45)
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    plt.title(title)
    plt.savefig(file_name + '.png', bbox_inches='tight')
    plt.savefig(file_name + '.pdf', bbox_inches='tight')


def analyze_cert_years_frequency(all_cert_items):
    scheme_date = {}
    level_date = {}
    archive_date = {}
    validity_length = {}
    valid_in_years = {}
    manufacturer_date = {}
    manufacturer_items = {}
    START_YEAR = 1997
    END_YEAR = datetime.datetime.now().year + 1
    ARCHIVE_OFFSET = 10

    for i in range(END_YEAR - START_YEAR + ARCHIVE_OFFSET):
        validity_length[i] = []

    valid_in_years['active'] = {}
    valid_in_years['archived'] = {}
    for year in range(START_YEAR, END_YEAR + ARCHIVE_OFFSET):
        valid_in_years['active'][year] = []
        valid_in_years['archived'][year] = []

    for cert_long_id in all_cert_items.keys():
        cert = all_cert_items[cert_long_id]
        if is_in_dict(cert, ['csv_scan', 'cc_certification_date']):
            # extract year of certification
            cert_date = cert['csv_scan']['cc_certification_date']
            parsed_date = parser.parse(cert_date)
            cert_year = parsed_date.year
            # try to extract year of archivation (if provided)
            archived_year = None
            if is_in_dict(cert, ['csv_scan', 'cc_archived_date']):
                cert_archive_date = cert['csv_scan']['cc_archived_date']
                if cert_archive_date != '':
                    archived_year = parser.parse(cert_archive_date).year

            # extract EAL level
            if is_in_dict(cert, ['csv_scan', 'cc_security_level']):
                level = cert['csv_scan']['cc_security_level']
                if level.find(',') != -1:
                    level = level[:level.find(',')]  # trim list of augmented items
                level_out = level
                if level == 'None':
                    if cert['csv_scan']['cc_protection_profiles'] != '':
                        level_out = 'Protection Profile'

                if level_out not in level_date.keys():
                    level_date[level_out] = {}
                    for year in range(START_YEAR, END_YEAR):
                        level_date[level_out][year] = []
                level_date[level_out][cert_year].append(cert_long_id)


            # extract scheme
            if is_in_dict(cert, ['csv_scan', 'cc_scheme']):
                cc_scheme = cert['csv_scan']['cc_scheme']
                if cc_scheme not in scheme_date.keys():
                    scheme_date[cc_scheme] = {}
                    for year in range(START_YEAR, END_YEAR):
                        scheme_date[cc_scheme][year] = []
                scheme_date[cc_scheme][cert_year].append(cert_long_id)

            # extract manufacturer(s)
            if 'cc_manufacturer_simple_list' in cert['processed']:
                for manufacturer in cert['processed']['cc_manufacturer_simple_list']:
                    if manufacturer not in manufacturer_date.keys():
                        manufacturer_date[manufacturer] = {}
                        for year in range(START_YEAR, END_YEAR):
                            manufacturer_date[manufacturer][year] = []
                    if manufacturer not in manufacturer_items:
                        manufacturer_items[manufacturer] = 0

                    manufacturer_date[manufacturer][cert_year].append(cert_long_id)
                    manufacturer_items[manufacturer] += 1

            # extract cert archival status
            if archived_year is not None:
                valid_years = archived_year - cert_year + 1
                validity_length[valid_years].append(cert_long_id)

                if 'archived_date' not in archive_date.keys():
                    archive_date['archived_date'] = {}
                    for year in range(START_YEAR, END_YEAR + ARCHIVE_OFFSET):  # archive year can be quite in future
                        archive_date['archived_date'][year] = []

                archive_date['archived_date'][archived_year].append(cert_long_id)

            # establish certificates active / archived in give year
            for year in range(START_YEAR, END_YEAR + ARCHIVE_OFFSET):
                if archived_year is not None:
                    # archived date is set
                    if year >= cert_year:
                        if year <= archived_year:
                            # certificate is valid in year
                            valid_in_years['active'][year].append(cert_long_id)
                        else:
                            # certificate is NOT valid in given year
                            valid_in_years['archived'][year].append(cert_long_id)
                else:
                    # no archival date set => active
                    if year >= cert_year:
                        # certificate is valid in year
                        valid_in_years['active'][year].append(cert_long_id)

    # print manufacturers frequency
    sorted_by_occurence = sorted(manufacturer_items.items(), key=operator.itemgetter(1))
    print('\n### Frequency of certificates per company')
    print('  # companies: {}'.format(len(manufacturer_items)))
    print('  # companies with more than 1 cert: {}'.format(len([i for i in sorted_by_occurence if i[1] > 1])))
    print('  # companies with more than 10 cert: {}'.format(len([i for i in sorted_by_occurence if i[1] > 10])))
    print('  # companies with more than 50 cert: {}\n'.format(len([i for i in sorted_by_occurence if i[1] > 50])))
    for manufacturer in sorted_by_occurence:
        print('  {}: {}x'.format(manufacturer[0], manufacturer[1]))

    # plot graphs showing cert. scheme and EAL in years
    years = np.arange(START_YEAR, END_YEAR)
    years_extended = np.arange(START_YEAR, END_YEAR + ARCHIVE_OFFSET)
    plot_schemes_multi_line_graph(years, scheme_date, ['DE', 'JP', 'FR', 'US', 'CA'], 'Year of issuance', 'Number of certificates issued', 'CC certificates issuance frequency per scheme and year', 'num_certs_in_years')
    plot_schemes_multi_line_graph(years, level_date, ['EAL4+', 'EAL5+','EAL2+', 'Protection Profile'], 'Year of issuance', 'Number of certificates issued', 'Certificates issuance frequency per EAL and year', 'num_certs_eal_in_years')
    plot_schemes_multi_line_graph(years_extended, archive_date, [], 'Year of issuance', 'Number of certificates', 'Number of certificates archived or planned for archival in a given year', 'num_certs_archived_in_years')
    plot_schemes_multi_line_graph(years_extended, valid_in_years, [], 'Year', 'Number of certificates', 'Number of certificates active and archived in given year', 'num_certs_active_archived_in_years')

    sc_manufacturers = ['Gemalto', 'NXP Semiconductors', 'Samsung', 'STMicroelectronics', 'Oberthur Technologies',
                        'Infineon Technologies AG', 'G+D Mobile Security GmbH', 'ATMEL Smart Card ICs', 'Idemia',
                        'Athena Smartcard', 'Renesas', 'Philips Semiconductors GmbH', 'Oberthur Card Systems']

    # plot only top manufacturers
    top_manufacturers = dict(sorted_by_occurence[len(sorted_by_occurence) - 20:]).keys()  # top 20 manufacturers
    plot_manufacturers_date = {}
    for manuf in manufacturer_date.keys():
        if manuf in top_manufacturers:
            plot_manufacturers_date[manuf] = manufacturer_date[manuf]
    plot_schemes_multi_line_graph(years, plot_manufacturers_date, sc_manufacturers, 'Year of issuance', 'Number of certificates issued', 'Top 20 manufacturers of certified items per year', 'manufacturer_in_years')

    # plot only smartcard manufacturers
    plot_manufacturers_date = {}
    for manuf in manufacturer_date.keys():
        if manuf in sc_manufacturers:
            plot_manufacturers_date[manuf] = manufacturer_date[manuf]
    plot_schemes_multi_line_graph(years, plot_manufacturers_date, [], 'Year of issuance', 'Number of certificates issued', 'Smartcard-related manufacturers of certified items per year', 'manufacturer_sc_in_years')

    # plot certificate validity lengths
    print('### Certificates validity period lengths:')
    validity_length_numbers = []
    for length in sorted(validity_length.keys()):
        print('  {} year(s): {}x   {}'.format(length, len(validity_length[length]), validity_length[length]))
        validity_length_numbers.append(len(validity_length[length]))
    plot_bar_graph(validity_length_numbers, sorted(validity_length.keys()), 'Number of certificates', 'Number of certificates with specific validity length', 'cert_validity_length_frequency')


def analyze_eal_frequency(all_cert_items):
    scheme_level = {}
    for cert_long_id in all_cert_items.keys():
        cert = all_cert_items[cert_long_id]
        if is_in_dict(cert, ['csv_scan', 'cc_scheme']):
            if is_in_dict(cert, ['csv_scan', 'cc_security_level']):
                cc_scheme = cert['csv_scan']['cc_scheme']
                level = cert['csv_scan']['cc_security_level']
                if level.find(',') != -1:
                    level = level[:level.find(',')]  # trim list of augmented items
                if cc_scheme not in scheme_level.keys():
                    scheme_level[cc_scheme] = {}
                if level not in scheme_level[cc_scheme]:
                    scheme_level[cc_scheme][level] = 0
                scheme_level[cc_scheme][level] += 1

    print('\n### CC EAL levels based on the certification scheme:')
    for cc_scheme in sorted(scheme_level.keys()):
        print(cc_scheme)
        for level in sorted(scheme_level[cc_scheme].keys()):
            print('  {:5}: {}x'.format(level, scheme_level[cc_scheme][level]))

    print('\n')
    eal_headers = ['EAL1', 'EAL1+','EAL2', 'EAL2+','EAL3', 'EAL3+','EAL4', 'EAL4+','EAL5',
                 'EAL5+','EAL6', 'EAL6+','EAL7', 'EAL7+', 'None']

    total_eals = {}
    for level in eal_headers:
        total_eals[level] = 0

    cc_eal_freq = []
    sum_total = 0
    for cc_scheme in sorted(scheme_level.keys()):
        this_scheme_levels = [cc_scheme]
        total = 0
        for level in eal_headers:
            if level in scheme_level[cc_scheme]:
                this_scheme_levels.append(scheme_level[cc_scheme][level])
                total += scheme_level[cc_scheme][level]
                total_eals[level] += scheme_level[cc_scheme][level]
            else:
                this_scheme_levels.append(0)

        this_scheme_levels.append(total)
        sum_total += total
        cc_eal_freq.append(this_scheme_levels)

    total_eals_row = []
    for level in sorted(total_eals.keys()):
        total_eals_row.append(total_eals[level])

    # plot bar graph with frequency of CC EAL levels
    plot_bar_graph(total_eals_row, eal_headers, 'Number of certificates', 'Number of certificates of specific EAL level', 'cert_eal_frequency')

    # Print table with results over national schemes
    total_eals_row.append(sum_total)
    cc_eal_freq.append(['Total'] + total_eals_row)
    print(tabulate(cc_eal_freq, ['CC scheme'] + eal_headers + ['Total']))


def analyze_sars_frequency(all_cert_items):
    sars_freq = {}
    for cert_long_id in all_cert_items.keys():
        cert = all_cert_items[cert_long_id]
        if is_in_dict(cert, ['keywords_scan', 'rules_security_target_class']):
            sars = cert['keywords_scan']['rules_security_target_class']
            for sar_rule in sars:
                for sar_hit in sars[sar_rule]:
                    if sar_hit not in sars_freq.keys():
                        sars_freq[sar_hit] = 0
                    sars_freq[sar_hit] += 1


    print('\n### CC security assurance components frequency:')
    sars_labels = sorted(sars_freq.keys())
    sars_freq_nums = []
    for sar in sars_labels:
        print('{:10}: {}x'.format(sar, sars_freq[sar]))
        sars_freq_nums.append(sars_freq[sar])

    print('\n### CC security assurance components frequency sorted by num occurences:')
    sorted_by_occurence = sorted(sars_freq.items(), key=operator.itemgetter(1))
    for sar in sorted_by_occurence:
        print('{:10}: {}x'.format(sar[0], sar[1]))

    # plot bar graph with frequency of CC SARs
    plot_bar_graph(sars_freq_nums, sars_labels, 'Number of certificates', 'Number of certificates mentioning specific security assurance component (SAR)\nAll listed SARs occured at least once', 'cert_sars_frequency')
    sars_freq_nums, sars_labels = (list(t) for t in zip(*sorted(zip(sars_freq_nums, sars_labels), reverse = True)))
    plot_bar_graph(sars_freq_nums, sars_labels, 'Number of certificates', 'Number of certificates mentioning specific security assurance component (SAR)\nAll listed SARs occured at least once', 'cert_sars_frequency_sorted')

    # plot heatmap of SARs frequencies based on type (row) and level (column)
    sars_labels = sorted(sars_freq.keys())
    sars_unique_names = []
    for sar in sars_labels:
        if sar.find('.') != -1:
            name = sar[:sar.find('.')]
        else:
            name = sar
        if name not in sars_unique_names:
            sars_unique_names.append(name)

    sars_unique_names = sorted(sars_unique_names)
    max_sar_level = 6
    num_sars = len(sars_unique_names)
    sar_heatmap = []
    sar_matrix = []
    for i in range(1, max_sar_level + 1):
        sar_row = []
        for name in sars_unique_names:
            sar_row.append(0)
        sar_matrix.append(sar_row)

    for sar in sorted_by_occurence:
        if sar[0].find('.') != -1:
            name = sar[0][:sar[0].find('.')]
            name_index = sars_unique_names.index(name)
            level = int(sar[0][sar[0].find('.') + 1:])
            sar_matrix[level - 1][name_index] = sar[1]

    # plot heatmap graph with frequency of SAR levels
    y_data_labels = range(1, max_sar_level + 2)
    plot_heatmap_graph(sar_matrix, sars_unique_names, y_data_labels, 'Security assurance component (SAR) class', 'Security assurance components (SAR) level', 'Frequency of achieved levels for Security assurance component (SAR) classes', 'cert_sars_heatmap')


def generate_dot_graphs(all_items_found, walk_dir):
    print_dot_graph(['rules_cert_id'], all_items_found, walk_dir, 'certid_graph.dot', True)
    print_dot_graph(['rules_javacard'], all_items_found, walk_dir, 'cert_javacard_graph.dot', False)

    #    print_dot_graph(['rules_security_level'], all_items_found, walk_dir, 'cert_security_level_graph.dot', True)
    #    print_dot_graph(['rules_crypto_libs'], all_items_found, walk_dir, 'cert_crypto_libs_graph.dot', False)
    #    print_dot_graph(['rules_vendor'], all_items_found, walk_dir, 'rules_vendor.dot', False)
    #    print_dot_graph(['rules_crypto_algs'], all_items_found, walk_dir, 'rules_crypto_algs.dot', False)
    #    print_dot_graph(['rules_protection_profiles'], all_items_found, walk_dir, 'rules_protection_profiles.dot', False)
    #    print_dot_graph(['rules_defenses'], all_items_found, walk_dir, 'rules_defenses.dot', False)
