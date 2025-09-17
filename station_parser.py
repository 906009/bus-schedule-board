import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from bs4 import BeautifulSoup
import re
from datetime import datetime
from aiogram.utils.deep_linking import create_start_link

urllib3.disable_warnings(InsecureRequestWarning)


class StationParser:
    def __init__(self, bot):
        self.bot = bot
        self.base_url = "https://transportrb.ru/wap/online/"

    async def sorter(self, store):
        lines = store.strip().split('\n')
        current_time = datetime.now()
        buses_times = []
        detailed_buses_times = []
        directions = []
        trans_link = []
        tracked = 0

        def replace_bus(bus):
            bus = bus.replace('🚍 Тб.', '🚎 ').replace('🚍 Тм.', '🚋 ')
            return bus

        for line in lines:
            line = line.strip("[]").replace("'", "").split(", ")
            if len(line) >= 3 and isinstance(line[0], str) and len(line[0]) > 0 and re.search(r'\d{2}:\d{2}', line[2]):
                bus = replace_bus("🚍 " + line[0])
                directions = line[1]
                time = line[2]
                trans_link = line[-1]
                buses_times.append((bus, directions, time, trans_link))
            if len(line) >= 3 and isinstance(line[0], str) and '(' in line[2]:
                bus = replace_bus("🚍 " + line[0])
                time = line[3]
                bus_time = current_time.replace(hour=datetime.strptime(time, '%H:%M').time().hour,
                                                minute=datetime.strptime(time, '%H:%M').time().minute, second=0,
                                                microsecond=0)
                distance = line[4].replace('(', '').replace(')', '') if len(line) > 3 else None
                time_left = int((bus_time - current_time).total_seconds() // 60)
                if time_left < 1:
                    time_left = "прибывает"
                else:
                    time_left = str(time_left) + " минут"
                detailed_buses_times.append((bus, time, distance, directions, time_left, trans_link))
                tracked += 1
        detailed_buses_times.sort(key=lambda x: datetime.strptime(x[1], '%H:%M'))
        opti_bus = {}
        for bus, time, distance, directions, time_left, trans_link in detailed_buses_times:
            key = (bus, directions)
            if key not in opti_bus:
                opti_bus[key] = []
            opti_bus[key].append((time_left, time, distance, trans_link))
        answer = f"\nОбновлено в {current_time.strftime('%H:%M:%S')}\nПолучение данных...\n\n"
        if tracked > 0:
            answer += "*Отслеживаемые:*\n"
        for key in opti_bus:
            bus, directions = key
            info = opti_bus[key]
            times_info = []
            for time_left, time, distance, trans_link in info:
                if time_left == "прибывает":
                    times_info.append(
                        f"Прибывает [Прогноз]({await create_start_link(self.bot, f'Рейс {trans_link}', encode=True)}) // [ГЕО]({await create_start_link(self.bot, f'ГЕО {trans_link}', encode=True)})")
                else:
                    times_info.append(
                        f"Ожидается через {time_left} в {time} ({distance}) [Прогноз]({await create_start_link(self.bot, f'Рейс {trans_link}', encode=True)}) // [ГЕО]({await create_start_link(self.bot, f'ГЕО {trans_link}', encode=True)})")
            times_info = "\n".join(times_info)
            answer += f"[{bus}]({await create_start_link(self.bot, f'Маршрут {bus}', encode=True)}), до *{directions}*\n{times_info}\n\n"
        if tracked < 3:
            answer += "\n*Расписание:*\n"
            opti_bus = {}
            for bus, directions, time, trans_link in buses_times:
                key = (bus, directions)
                if key not in opti_bus:
                    opti_bus[key] = []
                opti_bus[key].append((time, trans_link))
            for key in opti_bus:
                bus, directions = key
                info = opti_bus[key]
                rasp = []
                for time, trans_link in info:
                    if time.find("(") > 0:
                        time = time[:time.find("(")]
                    rasp.append(
                        f"Ожидается в {time} [Прогноз]({await create_start_link(self.bot, f'Рейс {trans_link}', encode=True)}) // [ГЕО]({await create_start_link(self.bot, f'ГЕО {trans_link}', encode=True)})")
                rasp = "\n".join(rasp)
                answer += f"[{bus}]({await create_start_link(self.bot, f'Маршрут {bus}', encode=True)}), до *{directions}*\n{rasp}\n\n"
        return answer

    async def parse(self, stations):
        answer = f"Обновлено в {datetime.now().strftime('%H:%M:%S')}\nПолучение данных...\n\nНет данных"
        store = ""
        for station in stations:
            station = station.strip()
            if not station:
                continue
            url = f"{self.base_url}?st_id={station}"
            response = requests.get(url, verify=False)
            response.encoding = 'utf-8'
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                rows = soup.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if cells:
                        data = []
                        trans_link = []
                        for cell in cells:
                            link = cell.find('a')
                            if link and link.get('href', '').startswith('?srv_id='):
                                trans_link = link['href']
                        for cell in cells:
                            cell_text = cell.get_text(strip=True)
                            if ">>" in cell_text and trans_link:
                                cell_text = cell_text.replace(">>", trans_link)
                            #link = cell.find('a')
                            #if link and "mr_id=530" in link.get('href', ''):
                            #    cell_text = cell_text.replace("51", "51А")
                            data.append(cell_text)
                        store = store + "\n" + str(data)
            else:
                answer = f"Ошибка запроса: {response.status_code}"
        if len(store) > 0:
            answer = await self.sorter(store)
        return answer
