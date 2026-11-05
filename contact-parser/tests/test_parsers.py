"""Офлайн-тесты разбора HTML: python -m unittest discover tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dou  # noqa: E402
import linkedin  # noqa: E402
from common import Person, StopRun, normalize_url, split_headline, split_name  # noqa: E402
from runner import describe, detect, read_links  # noqa: E402
from sheets import CsvStore  # noqa: E402

DOU_COMPANY = """
<div class="company-info"><img class="logo"><h1 class="g-h2">  EPAM  </h1>
 понад 1500 спеціалістів
 <div class="offices bi">Київ, Львів</div>
 <div class="site"><a href="https://careers.epam.ua/" rel="nofollow">careers.epam.ua</a></div></div>"""

DOU_OFFICES = """
<div class="info"><h5>Адміністрація</h5><ul class="persons">
<li><a class="name" href="https://dou.ua/users/anatolij-6/"><div class="g-avatar"><img alt="x"></div>
 Anatoliy Visikirsky</a><br> Director, People Operations &amp; Technology</li>
<li><a class="name" href="https://dou.ua/users/no-title/">Ivan Franko</a></li>
<li><a class="name" href="https://dou.ua/users/anatolij-6/">Anatoliy Visikirsky</a><br>dup</li>
</ul></div>"""

DOU_USER = """<div class="b-user-info"><h1>Anatoliy Visikirsky <a class="va"></a></h1></div>
<div class="descr">Director, People Operations в <a class="company" href="https://jobs.dou.ua/companies/grammarly/">
<span>Superhuman (formerly Grammarly)</span></a></div>"""

DOU_LIST = """<ul><li class="l-company"><div class="company"><div class="h2">
<a class="cn-a" href="https://jobs.dou.ua/companies/boosta/">Boosta</a></div></div></li></ul>
<div class="company"><div class="h2"><a class="cn-a" href="/companies/wild-hornets/">WH</a></div></div>"""

LI_ABOUT = """<main><h1><span>Grammarly</span></h1><dl>
<dt><h3>Website</h3></dt><dd><a href="https://www.linkedin.com/redir?url=x"><span>https://www.grammarly.com</span></a></dd>
<dt><h3>Industry</h3></dt><dd>Software Development</dd>
<dt><h3>Company size</h3></dt><dd>1,001-5,000 employees <span>1,234 on LinkedIn</span></dd>
<dt><h3>Headquarters</h3></dt><dd>San Francisco, CA</dd></dl></main>"""

LI_ABOUT_UK = """<main><h1>Acme</h1><dl>
<dt>Вебсайт</dt><dd><a href="#">acme.ua</a></dd>
<dt>Розмір компанії</dt><dd>51–200 працівників</dd>
<dt>Штаб-квартира</dt><dd>Київ</dd></dl></main>"""

LI_PEOPLE = """<header><a href="/in/me/">Me</a></header><main><ul>
<li class="org-people-profile-card__profile-card-spacing"><section>
  <a href="https://www.linkedin.com/in/jane-doe-123/?miniProfileUrn=abc"><img alt=""></a>
  <div class="artdeco-entity-lockup__title"><a href="/in/jane-doe-123/">Jane Doe, MBA</a></div>
  <div class="artdeco-entity-lockup__badge">· 2nd</div>
  <div class="artdeco-entity-lockup__subtitle">Head of Sales at Grammarly | Ex-Google</div>
  <button>Connect</button></section></li>
<li class="org-people-profile-card__profile-card-spacing"><section>
  <div class="artdeco-entity-lockup__title">LinkedIn Member</div>
  <div class="artdeco-entity-lockup__subtitle">Engineer</div></section></li>
<li class="org-people-profile-card__profile-card-spacing"><section>
  <a href="/in/john-smith/"><div class="artdeco-entity-lockup__title">John Smith</div></a>
  <div class="artdeco-entity-lockup__subtitle">Product Designer</div></section></li>
</ul></main>"""

LI_SEARCH = """<main><ul role="list">
<li><div><a href="https://www.linkedin.com/in/olena-k/?mini=1"><span aria-hidden="true">Olena Koval</span>
 <span class="visually-hidden">View Olena Koval’s profile</span></a>
 <span>• 2nd</span><span>2nd degree connection</span>
 <div>CTO @ SoftServe</div><div>Lviv, Ukraine</div>
 <p>Current: Chief Technology Officer at SoftServe Inc</p><button>Connect</button></div></li>
<li><div><a href="/in/petro-b/"><span aria-hidden="true">Petro Bondar</span></a>
 <div>Founder</div><div>Kyiv</div></div></li>
</ul></main>"""

LI_PROFILE = """<main><section><h1>Mariia Ivanenko</h1>
<div class="text-body-medium break-words">VP Marketing at Acme | B2B</div>
<button aria-label="Current company: Acme Corp. Click to skip to experience card"></button></section></main>"""


class TestCommon(unittest.TestCase):
    def test_split_name(self):
        self.assertEqual(split_name("Jane Doe, MBA"), ("Jane", "Doe"))
        self.assertEqual(split_name("Anna Maria Lee"), ("Anna", "Maria Lee"))
        self.assertEqual(split_name("Олена 🚀"), ("Олена", ""))
        self.assertEqual(split_name(""), ("", ""))
        self.assertEqual(split_name("Olena (Lena) Koval"), ("Olena", "Koval"))
        self.assertEqual(split_name("Ivan Petrenko [he/him], PMP"), ("Ivan", "Petrenko"))

    def test_split_headline(self):
        self.assertEqual(split_headline("CEO at Acme | Investor"), ("CEO", "Acme"))
        self.assertEqual(split_headline("CTO @ SoftServe"), ("CTO", "SoftServe"))
        self.assertEqual(split_headline("Recruiter"), ("Recruiter", ""))
        self.assertEqual(split_headline("CEO в компании Acme"), ("CEO", "Acme"))
        self.assertEqual(split_headline("Software Engineer in Kyiv"), ("Software Engineer in Kyiv", ""))

    def test_normalize(self):
        self.assertEqual(normalize_url("https://www.linkedin.com/in/Jane-Doe?x=1"),
                         "https://linkedin.com/in/jane-doe/")
        self.assertEqual(normalize_url("ua.linkedin.com/company/acme"), "https://linkedin.com/company/acme/")
        self.assertEqual(normalize_url("https://jobs.dou.ua/companies/epam-systems"),
                         "https://jobs.dou.ua/companies/epam-systems/")

    def test_detect(self):
        self.assertEqual(detect("https://jobs.dou.ua/companies/epam-systems/offices/"), ("dou", "company"))
        self.assertEqual(detect("https://jobs.dou.ua/companies/?city=Львів"), ("dou", "company_list"))
        self.assertEqual(detect("https://dou.ua/users/x/"), ("dou", "person"))
        self.assertEqual(detect("https://www.linkedin.com/company/acme/"), ("linkedin", "company"))
        self.assertEqual(detect("https://www.linkedin.com/company/acme/people/?keywords=ceo"),
                         ("linkedin", "company_people"))
        self.assertEqual(detect("https://www.linkedin.com/search/results/people/?keywords=cto"),
                         ("linkedin", "search"))
        self.assertEqual(detect("https://linkedin.com/in/jane/"), ("linkedin", "person"))
        self.assertIsNone(detect("https://example.com/"))
        self.assertIsNone(detect("https://www.linkedin.com/feed/"))

    def test_describe(self):
        d = describe("https://www.linkedin.com/company/acme/people/")
        self.assertEqual((d["ok"], d["source"], d["label"]), (True, "linkedin", "компания + люди"))
        self.assertFalse(describe("https://www.linkedin.com/feed/")["ok"])
        self.assertIn("не dou.ua", describe("https://example.com/")["reason"])

    def test_read_links(self):
        self.assertEqual(read_links("\n# c\nhttps://a.ua/\n jobs.dou.ua/x \nhttps://a.ua/\n"),
                         ["https://a.ua/", "https://jobs.dou.ua/x"])


class TestDou(unittest.TestCase):
    def test_company(self):
        c = dou.parse_company(DOU_COMPANY, "https://jobs.dou.ua/companies/epam-systems/")
        self.assertEqual((c.name, c.website, c.city, c.size),
                         ("EPAM", "https://careers.epam.ua/", "Київ, Львів", "понад 1500 спеціалістів"))

    def test_people(self):
        ps = dou.parse_people(DOU_OFFICES, "Grammarly")
        self.assertEqual(len(ps), 2)
        self.assertEqual((ps[0].first_name, ps[0].last_name, ps[0].title, ps[0].company),
                         ("Anatoliy", "Visikirsky", "Director, People Operations & Technology", "Grammarly"))
        self.assertEqual(ps[1].title, "")

    def test_user(self):
        p = dou.parse_user(DOU_USER, "https://dou.ua/users/anatolij-6/")
        self.assertEqual((p.first_name, p.title, p.company),
                         ("Anatoliy", "Director, People Operations", "Superhuman (formerly Grammarly)"))

    def test_list(self):
        self.assertEqual(dou.parse_company_list(DOU_LIST), ["https://jobs.dou.ua/companies/boosta/",
                                                            "https://jobs.dou.ua/companies/wild-hornets/"])


class TestLinkedIn(unittest.TestCase):
    def test_company(self):
        c = linkedin.parse_company(LI_ABOUT, "https://www.linkedin.com/company/grammarly/about/")
        self.assertEqual((c.name, c.website, c.size, c.city, c.url),
                         ("Grammarly", "https://www.grammarly.com", "1,001-5,000 employees", "San Francisco, CA",
                          "https://linkedin.com/company/grammarly/"))
        c = linkedin.parse_company(LI_ABOUT_UK, "https://www.linkedin.com/company/acme/")
        self.assertEqual((c.website, c.size, c.city), ("acme.ua", "51–200 працівників", "Київ"))

    def test_company_missing_fields(self):
        c = linkedin.parse_company("<main><h1>Only Name</h1></main>", "https://www.linkedin.com/company/x/")
        self.assertEqual((c.name, c.website, c.size, c.city), ("Only Name", "", "", ""))

    def test_people_tab(self):
        ps = linkedin.parse_people_cards(LI_PEOPLE, default_company="Grammarly")
        self.assertEqual([(p.first_name, p.last_name, p.title, p.company, p.url) for p in ps], [
            ("Jane", "Doe", "Head of Sales", "Grammarly", "https://linkedin.com/in/jane-doe-123/"),
            ("John", "Smith", "Product Designer", "Grammarly", "https://linkedin.com/in/john-smith/"),
        ])

    def test_search(self):
        ps = linkedin.parse_people_cards(LI_SEARCH)
        self.assertEqual([(p.first_name, p.last_name, p.title, p.company) for p in ps], [
            ("Olena", "Koval", "Chief Technology Officer", "SoftServe Inc"),
            ("Petro", "Bondar", "Founder", ""),
        ])

    def test_profile(self):
        p = linkedin.parse_profile(LI_PROFILE, "https://www.linkedin.com/in/mariia-i/")
        self.assertEqual((p.first_name, p.last_name, p.title, p.company, p.url),
                         ("Mariia", "Ivanenko", "VP Marketing", "Acme Corp", "https://linkedin.com/in/mariia-i/"))

    def test_guards(self):
        with self.assertRaises(StopRun):
            linkedin.check_page("https://www.linkedin.com/checkpoint/challenge/x", "")
        with self.assertRaises(StopRun):
            linkedin.check_page("https://www.linkedin.com/login", "")
        with self.assertRaises(StopRun):
            linkedin.check_page("https://www.linkedin.com/feed/", "<p>Let's do a quick security check</p>")
        linkedin.check_page("https://www.linkedin.com/in/x/", LI_PROFILE)  # без исключения
        # фраза из чужого профиля не должна останавливать запуск
        bio = "<main><h1>Anna</h1><section><p>I detect unusual activity in payments</p></section></main>"
        linkedin.check_page("https://www.linkedin.com/in/anna/", bio)
        with self.assertRaises(StopRun):
            linkedin.check_page("https://www.linkedin.com/search/results/people/",
                                "<main><section>You've reached the commercial use limit on search</section></main>")

    def test_profile_ignores_other_company_labels(self):
        html = LI_PROFILE.replace("<button aria-label=\"Current", "<button aria-label=\"Follow company: Google\"></button>"
                                  "<button aria-label=\"Current")
        self.assertEqual(linkedin.parse_profile(html, "https://www.linkedin.com/in/m/").company, "Acme Corp")

    def test_session_info(self):
        import sqlite3
        import time
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(linkedin.session_info(d)["status"], "out")
            db = Path(d) / "Default" / "Network"
            db.mkdir(parents=True)
            con = sqlite3.connect(db / "Cookies")
            con.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, expires_utc INTEGER)")
            future = int((time.time() + 11644473600 + 86400 * 30) * 1e6)
            con.execute("INSERT INTO cookies VALUES ('.www.linkedin.com', 'li_at', ?)", (future,))
            con.commit()
            con.close()
            self.assertEqual(linkedin.session_info(d)["status"], "in")


class TestStore(unittest.TestCase):
    def test_csv_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            s = CsvStore(d)
            p = Person("A", "B", "CEO", "X", "https://www.linkedin.com/in/ab/", "linkedin")
            self.assertEqual(len(s.add_people([p, p])), 1)
            s2 = CsvStore(d)  # повторный запуск
            p2 = Person("A", "B", "CEO", "X", "https://linkedin.com/in/ab?x=1", "linkedin")
            self.assertEqual(s2.add_people([p2]), [])


if __name__ == "__main__":
    unittest.main()
