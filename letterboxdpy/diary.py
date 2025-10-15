if __loader__.name == '__main__':
    import sys
    sys.path.append(sys.path[0] + '/..')

import re
import os
import csv
from json import (
    dumps as json_dumps,
    loads as json_loads
)

from letterboxdpy.core.encoder import SecretsEncoder
from letterboxdpy.pages import user_diary
from letterboxdpy.core.exceptions import PrivateRouteError



class Diary:

    class DiaryPages:
        def __init__(self, username: str) -> None:
            self.diary = user_diary.UserDiary(username)

    def __init__(self, username: str) -> None:
        assert re.match("^[A-Za-z0-9_]+$", username), "Invalid author"
        self.username = username
        self.pages = self.DiaryPages(self.username)
        self.url = self.get_url()
        self._entries = None

    # Properties
    @property
    def entries(self) -> dict:
        if self._entries is None:
            self._entries = self.get_entries()
        return self._entries

    # Magic Methods
    def __str__(self) -> str:
        return json_dumps(self, indent=2, cls=SecretsEncoder, secrets=['pages'])

    def jsonify(self) -> dict:
        return json_loads(self.__str__())

    # Data Retrieval Methods
    def get_url(self) -> str:
        return self.pages.diary.url
    def get_entries(self) -> dict:
        return self.pages.diary.get_diary()


if __name__ == "__main__":
    import argparse
    import sys

    sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description="Fetch a user's diary.")
    parser.add_argument('--user', '-u', help="Username to fetch diary for", required=False)
    parser.add_argument('--debug', action='store_true', help='Print debug info about first diary entry')
    args = parser.parse_args()

    username = args.user or input('Enter username: ').strip()

    while not username:
        username = input('Please enter a valid username: ').strip()

    print(f"Fetching diary for username: {username}")

    try:
        diary_instance = Diary(username)
        print('URL:', diary_instance.url)
        entries = diary_instance.entries
        if args.debug:
            # print a short debug summary of the first entry
            sample = None
            if isinstance(entries, dict) and 'entries' in entries:
                vals = list(entries['entries'].values())
                sample = vals[0] if vals else None
            elif isinstance(entries, dict):
                vals = [v for v in entries.values() if isinstance(v, dict)]
                sample = vals[0] if vals else None
            elif isinstance(entries, list):
                sample = entries[0] if entries else None
            print('DEBUG sample entry:', sample)
        entries = diary_instance.entries
        if entries:
            output_dir = os.path.join(os.path.dirname(__file__), 'output_csv')
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f'diary_{username}.csv')

            # Normalize structure
            if isinstance(entries, dict):
                # Case 1: {'entries': {id: entry, ...}, 'count': N, ...}
                if 'entries' in entries and isinstance(entries['entries'], dict):
                    entries_list = list(entries['entries'].values())
                # Case 2: dict of entries keyed by id: {id: entry, ...}
                elif all(isinstance(v, dict) for v in entries.values()):
                    entries_list = list(entries.values())
                else:
                    # fallback: look for lists inside values
                    possible_lists = [v for v in entries.values() if isinstance(v, list)]
                    if possible_lists:
                        entries_list = [item for sublist in possible_lists for item in sublist]
                    else:
                        entries_list = []
            elif isinstance(entries, list):
                entries_list = entries
            else:
                entries_list = []

            # Filter only dicts
            entries_list = [e for e in entries_list if isinstance(e, dict)]

            # Only keep specified headers and flatten nested fields
            fieldnames = ["name", "slug", "id", "release", "runtime", "rewatched", "rating", "liked", "reviewed", "date"]
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for entry in entries_list:
                    actions = entry.get('actions', {}) if isinstance(entry.get('actions', {}), dict) else {}
                    date_obj = entry.get('date', {}) if isinstance(entry.get('date', {}), dict) else {}
                    # format date as YYYY-MM-DD if possible
                    if date_obj and all(k in date_obj and date_obj[k] is not None for k in ('year', 'month', 'day')):
                        try:
                            date_str = f"{int(date_obj['year']):04d}-{int(date_obj['month']):02d}-{int(date_obj['day']):02d}"
                        except Exception:
                            date_str = str(date_obj)
                    else:
                        date_str = str(date_obj) if date_obj else ''

                    row = {
                        'name': entry.get('name', '') or '',
                        'slug': entry.get('slug', '') or '',
                        'id': entry.get('id', '') or '',
                        'release': entry.get('release', '') or '',
                        'runtime': entry.get('runtime', '') or '',
                        'rewatched': actions.get('rewatched', ''),
                        'rating': actions.get('rating', ''),
                        'liked': actions.get('liked', ''),
                        'reviewed': actions.get('reviewed', ''),
                        'date': date_str,
                    }
                    # Ensure all values are simple scalars for CSV
                    for k, v in row.items():
                        if isinstance(v, bool):
                            row[k] = '1' if v else '0'
                        elif v is None:
                            row[k] = ''
                        else:
                            row[k] = str(v)
                    writer.writerow(row)
            print(f"✅ Diary saved to: {output_path}")
        else:
            print("⚠️ No entries found.")
    except PrivateRouteError:
        print(f"Error: User's diary is private.")
    except Exception as e:
        print(f"⚠️ Failed to save diary to CSV: {e}")
        print(f"⚠️ Failed to save diary to CSV: {e}")
