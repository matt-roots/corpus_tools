"""
Makes fuzzy matches from a list of novel titles to a corpus manifest
"""
import os
import csv
import argparse
from pathlib import Path

kChadwyckTitle = "title"
kGaleTitle = 'display_title'
kChicagoTitle = 'TITLE'
kTitleFields = [kChicagoTitle, kChadwyckTitle, kGaleTitle]

kBadMatchFile = Path('./bad_matches.csv')  # needs global state to be appended to after each metadata table is processed

class Corpus:
    """
    Class containing metadata records for all items in the corpus
    """
    kStopWords = ('the', 'of', 'a', 'an', 'in', 'on', 'and')

    def __init__(self, path):
        self.metatable = path
        self.records = {}
        self.len = 0
        self.field_names = []
        self.id_count = 0

    def read_metatable(self):
        """
        Reads the metadata table and stores each item as a corresponding object in self.records
        :return:
        """
        print(f'Reading metadata from {self.metatable}')
        with open(self.metatable, encoding='UTF-8') as table:
            dialect = csv.Sniffer().sniff(table.read(12000), delimiters='\t,')
            table.seek(0)
            reader = csv.DictReader(table, dialect=dialect)
            print('Found the following headers:', reader.fieldnames)
            self.field_names = reader.fieldnames
            title_field = self.get_title_field(reader.fieldnames)
            print(f'Title field found: {title_field}')
            if not title_field:
                raise KeyError(f"Could not find valid title field for {self.metatable}")
            count = 0
            for row in reader:
                # process metadata to get title to store record
                raw_title = row[title_field]
                title = self.get_title(raw_title)
                if title in self.records:
                    print(f'Title collision detected for {raw_title}; skipping')
                    continue
                self.records[title] = Record(title, row, title_field)
                count += 1
            self.len += count
            print(f'Read all {count} rows from {self.metatable}')

    @staticmethod
    def get_title_field(row):
        """
        Returns a title field based off the titles included in kTitleFields
        """
        for field in row:
            if field in kTitleFields:
                return field
        else:
            return None

    def get_title(self, title):
        """
        lowercases, punctuation strips and removes common stopwords and appends author name (to reduce collisions)
        """
        t_words = [word.lower().strip(',.:;\'\"') for word in title.split()
                   if word.lower().strip(',.:;\'\"') not in Corpus.kStopWords]
        title = '_'.join(t_words) + '_' + str(self.id_count)
        self.id_count += 1
        return title


class Record:
    """
    Basic record containing metadata. Associated with some form of unique ID (a string)
    """

    def __init__(self, id_name, metadata, title_field):
        self.id = id_name
        self.title = metadata[title_field]
        self.metadata = metadata


def get_titles(path, col_num, title_header: bool):
    """
    Reads title info from file. Title header and col_num are drawn from command line args
    """
    titles = []
    with open(path) as title_table:
        reader = csv.reader(title_table)
        if title_header:
            reader.__next__()
        for row in reader:
            titles.append(row[col_num].replace('-', ' '))
    return titles


kMatchThreshold = 0.5
def filter_matches(matches):
    """
    filters matches to exclude any matches with fewer than threshold percentage matching terms; returning the reduced
    dictionary
    :param matches: dict mapping title (str) -> metadata record object:
    """
    with open(kBadMatchFile, mode='a', encoding='UTF-8') as f:
        writer = csv.writer(f, dialect=csv.unix_dialect)
        for match in list(matches):
            title_len = len(match.split())
            num_terms_matched = 0
            for word in matches[match].title.split():
                metadata_title = matches[match].title
                word = word.strip(',.:;?').lower()
                if word in match:
                    num_terms_matched += 1
            match_percent = num_terms_matched / title_len
            if match_percent <= kMatchThreshold:
                print(f'Removing unlikely match {match} -> {metadata_title} (percent match: '
                      f'{num_terms_matched / title_len})')
                writer.writerow([match, metadata_title, match_percent])
                del matches[match]


def match_titles(titles: list, corpus):
    """
    returns a dictionary matching titles to metadata records
    """
    matches = {}
    for title in titles:
        # print(f'matching raw title: {title}')
        search_title = [word for word in title.split() if word not in corpus.kStopWords]
        # print(f'parsed title into {search_title}')
        # set up recursive matching
        cur_word = max(search_title, key=len)
        # print(f'Matching titles containing: {cur_word}')
        candidates = [record for record in corpus.records if cur_word in record.split('_')]
        # print(f'Found candidates: {candidates}')
        if len(candidates) == 0:
            # print(f'No matches found for {title}')
            continue
        if len(candidates) == 1:
            # print(f'matched {title} to {candidates[0]}')
            matches[title] = corpus.records[candidates[0]]
        else:
            search_title.remove(cur_word)
            match = get_match(search_title, candidates)
            if match is not None:
                # print(f'matched {title} to {match}')
                matches[title] = corpus.records[match]
            else:
                # print(f'No matches found for {title}')
                pass
    filter_matches(matches)
    return matches

def get_match(title, candidates):
    """
    Recursively pares down a list of candidate matches by matching the longest word in the title against the list, then
    the second longest, etc
    """
    if len(title) == 0:
        return None
    else:
        cur_word = max(title, key=len)
        new_candidates = [candidate for candidate in candidates if cur_word in candidate.split('_')]
        if len(new_candidates) == 1:
            return new_candidates[0]
        else:
            title.remove(cur_word)
            return get_match(title, new_candidates)


def confirm(question):
    check = str(input(question + " (Y/N): ")).lower().strip()
    try:
        if check[0] == 'y':
            return True
        elif check[0] == 'n':
            return False
        else:
            print('Invalid Input')
            return confirm(question)
    except IndexError:
        print('Invalid Input')
        return confirm(question)


def main():
    """
    Reads all the metadata tables in a corpus directory, and attempts to match titles in each to a list of titles
    supplied via the titles table
    """
    # argparse setup
    parser = argparse.ArgumentParser(description='Fuzzy match texts to metadata tables')
    parser.add_argument('--metadata_dir', '-m', type=str, required=True,
                        help='path to the metadata directory')
    parser.add_argument('--titles', '-t', type=str, required=True, help='path to the table of titles to match')
    parser.add_argument('--title_col', '-n', type=int, required=False, default=0, help="0-based col index for titles "
                                                                                       "from table (default = 0)")
    parser.add_argument('--title_header', '-d', type=bool, required=False, default=False,
                        help="Indicates that the list of titles includes a header row")
    args = parser.parse_args()

    metadata_dir = Path(args.metadata_dir).resolve()  # get an absolute path
    titles_path = Path(args.titles).resolve()
    title_col = args.title_col
    title_header = args.title_header

    if kBadMatchFile.exists():
        print(f"Truncating {kBadMatchFile} for new matching")
        if confirm("Ok to continue?"):
            os.remove(kBadMatchFile)
        else:
            print("Aborting...")
            return 0

    # read the titles to match in:
    titles = get_titles(titles_path, title_col, title_header)
    print(f"Found titles to match from {titles_path} starting with:")
    print(*titles[:5], sep='\n')

    for file in metadata_dir.iterdir():
        if not (file.name.endswith('.csv') or file.name.endswith('.tsv')):
            continue
        print(f'Reading metadata table {file.name}')
        cur_corpus = Corpus(file)
        cur_corpus.read_metatable()
        matches = match_titles(titles, cur_corpus)
        outfile = file.name[:-4] + '_matches.csv'
        with open(outfile, 'w', encoding='UTF-8') as f:
            writer = csv.writer(f, dialect=csv.unix_dialect)
            header = ['match_title'] + cur_corpus.field_names
            writer.writerow(header)
            for title, record in matches.items():
                row = [title] + list(record.metadata.values())
                writer.writerow(row)
        print(f'Wrote probable matches to {outfile}')


if __name__ == '__main__':
    main()
