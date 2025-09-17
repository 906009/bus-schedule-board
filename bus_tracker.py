import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
from aiogram.utils.deep_linking import create_start_link
import asyncio


class TransportParser:
    def __init__(self, bot):
        self.bot = bot

    def parser(self, endpoint):
        response = requests.get("https://transportrb.ru/wap/" + endpoint, verify=False)
        return BeautifulSoup(response.text, 'html.parser')


class RouteInfo(TransportParser):
    async def get_route_info(self, link):
        soup = self.parser("online/" + link)
        info = soup.find_all('h1')
        route = info[2].get_text().strip().split(": ")[1]
        dst = info[3].get_text().strip().split(': ')[1]
        return route, dst


class BusInfo(TransportParser):
    async def get_bus_info(self, link):
        soup = self.parser("online/" + link)
        links = soup.find_all('h1')
        try:
            num = links[2].get_text().strip().split(": ")[1]
        except:
            num = "00"
        try:
            model = links[3].get_text().strip().split(": ")[1]
        except:
            model = "None"
        try:
            dst = links[5]
        except:
            dst = "None"
        info = [num, model, dst]
        return info


class ScheduleParser(TransportParser):
    async def get_schedule(self, link, links, ot):
        soup = self.parser(f'rasp{link}&{links[ot].get("href")[1:]}&rc_kkp=Bp')
        current_date_with_time = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        col = 0
        cur = int(current_date_with_time.timestamp())
        while soup.find("Нет данных.") is not None or col < 3:
            tom = cur + 86400
            link = link.replace(str(cur)[:str(cur).find(".0")], str(tom)[:str(tom).find(".0")])
            soup = self.parser(f'rasp{link}&{links[ot].get("href")[1:]}&rc_kkp=Bp')
            cur = tom
            col += 1
            await asyncio.sleep(1)
        hours = soup.find_all('td', style=re.compile(r'border'))
        times = []
        for hour in hours:
            h = hour.get_text().strip()
            table = hour.find_next('table')
            if table:
                minutes = table.find_all('td')
                for m in minutes:
                    m = m.get_text().strip()
                    if len(m) > 2:
                        m = m[:2]
                    if m != '':
                        time = datetime.strptime(f"{h}:{m}", "%H:%M")
                        times.append(time)
        total_interval = 0
        if len(times) > 1:
            for i in range(1, len(times)):
                if times[i] < times[i - 1]:
                    times[i] += timedelta(days=1)
                interval = times[i] - times[i - 1]
                total_interval += interval.total_seconds()
            interval = int((total_interval / (len(times) - 1)) // 60)
            data = [f'{times[0].strftime("%H:%M")}-{times[-1].strftime("%H:%M")}', interval]
        else:
            data = ["NaN", "NaN"]
        return data


class BusTracker(TransportParser):
    async def route_tracker(self, link, schedule=True):
        current_date_with_time = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        dt = str(current_date_with_time.timestamp())
        if dt.find(".0"):
            dt = dt[:dt.find(".0")]
        link = link.replace('1731956400', dt)
        soup = self.parser("online/" + link)
        links = soup.find_all('a')
        info = soup.find_all('h1')
        times = ""
        if "fm=1" in link:
            times = soup.find_all('td', string=re.compile(r'\d{2}:\d{2}'))
        elif "fm=0" in link:
            times = soup.find_all('td', string=re.compile(r' ч| мин|\xa0'))
        type_ts = info[1].get_text().strip().split(": ")[1]
        route = info[2].get_text().strip().split(": ")[1]
        if "mr_id=530" in link:
            route = "51А"
        dst = info[3]
        if links[4].get_text().strip() == dst:
            ot = 5
        else:
            ot = 4
        if schedule:
            wtai = await ScheduleParser(self).get_schedule(link, links, ot)
            work_time = wtai[0]
            interval = wtai[1]
        else:
            work_time = "NaN"
            interval = "NaN"
        data = f"Обновлено в {datetime.now().strftime('%H:%M:%S')}\n\nМаршрут: *{route}*\nВид транспорта: *{type_ts}*\nНаправление: *{dst.get_text().strip().split(': ')[1]}*\nГрафик работы: *{work_time}*\nИнтервал: *{interval} мин*\n\n"
        times_bs4 = times
        times = []
        for i in range(len(times_bs4)):
            if times_bs4:
                time = times_bs4.pop(0)
                if re.search(r' ч', time.get_text().strip()):
                    times.append(str(int(time.get_text().strip().split(" ч")[1]) + int(
                        time.get_text().strip().split(" ч")[0]) * 60) + " мин")
                else:
                    times.append(str(time.text.strip()))
            else:
                times.append("NaN")
        if "fm=1" in link:
            if len(links[ot:-5]) > len(times):
                for i, (link, time) in enumerate(zip(links[ot:-5], times)):
                    href = link.get('href')
                    if str(href).startswith('?srv_id='):
                        times.insert(i, "NaN")
        if len(links[ot:-5]) > len(times):
            for i in range(len(links[ot:-5]) - len(times)):
                times.insert(0, "NaN")
        for i, time in enumerate(times):
            if time == "":
                times[i] = "NaN"
        for link, time in zip(links[ot:-5], times):
            href = link.get('href')
            text = link.get_text().strip()
            if str(href).startswith('?srv_id='):
                model = (await BusInfo(self).get_bus_info(href))[1]
                ans = ""
                if type_ts == "Троллейбус":
                    ans += "🚎 "
                elif type_ts == "Трамвай":
                    ans += "🚃 "
                else:
                    ans += "🚍 "
                ans += f"*{model}* До остановки: {str(text)[1:-1]} [Прогноз]({await create_start_link(self.bot, f'Рейс {href}', encode=True)})"
                data += str(ans) + "\n"
            else:
                import main
                abbr = await main.abbreviationer_with_original(str(text))
                if len(abbr) > 1:
                    name = abbr[1]
                else:
                    name = abbr[0]
                if time == "NaN":
                    data += name + "\n"
                else:
                    data += time + " - " + name + "\n"
        return data

    async def current_bus_tracking(self, link):
        bus_data = await BusInfo(self).get_bus_info(link)
        href = bus_data[2]
        href = str((href.find('a'))['href'])
        data = await self.route_tracker(href + "&fm=0")
        tg_link = await create_start_link(self.bot, f'Рейс {str(link)}', encode=True)
        data_filter = ""
        route = data[data.rfind("Маршрут: "):data.rfind("\nВид транспорта:")]
        if tg_link in data:
            data = data[data.rfind(tg_link) + len(tg_link) + 1:].splitlines()
            for line in data:
                if "t.me" not in line:
                    data_filter += line + "\n"
            data = data_filter
            data = data.splitlines()
            temp_data = ""
            g_time = 0
            last_time = 0
            for i, line in enumerate(data):
                if line and line[0].isdigit():
                    time = int(line.split()[0])
                    if "- " in line:
                        dst = line.split("- ")[1]
                    else:
                        dst = "NaN"
                    if i != 0 and last_time <= time:
                        tt = abs(time - last_time)
                    else:
                        tt = time
                    last_time = time
                    g_time += tt
                    temp_data += str(g_time) + " мин - " + dst + "\n"
            data = temp_data
        else:
            data = ""

        num_ts = bus_data[0]
        model = bus_data[1]
        dst_num = bus_data[2]

        data = f"Обновлено в {datetime.now().strftime('%H:%M:%S')}\nПолучение данных...\n\nМаршрут: {route[route.rfind(' '):]}\nГос./гараж.номер: *{num_ts}*\nМодель: *{model}*\nНаправление: *{dst_num.get_text().strip().split(': ')[1]}*\n[Геопозиция]({await create_start_link(self.bot, f'ГЕО {link}', encode=True)})\n\n" + data
        return data
