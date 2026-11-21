from pediatrics.reviews import extract_aggregate_rating
from pediatrics.score import combined_rating, now_rank_key, score
from pediatrics.status import Status, check_clinic, find_reservation_links, parse_status_text


def test_waiting_and_current_number_fullwidth():
    st = parse_status_text("ただいま受付中です　現在の呼出番号：１２番　待ち人数　５人")
    assert st.state == "accepting"
    assert st.current_number == 12
    assert st.waiting == 5


def test_waiting_derived_from_numbers():
    st = parse_status_text("診察中の番号 10番 次にお取りできる番号 16")
    assert st.current_number == 10 and st.next_number == 16
    assert st.waiting == 5


def test_closed():
    st = parse_status_text("本日の受付は終了しました。またのご利用をお待ちしております")
    assert st.state == "closed"


def test_full():
    st = parse_status_text("本日の予約枠がありません")
    assert st.state == "full"


def test_unknown_text():
    st = parse_status_text("当院は地域のかかりつけ医として診療しています")
    assert st.state == "unknown" and st.waiting is None


def test_find_links_prefers_known_system():
    html = """
    <a href="/about">当院について</a>
    <a href="/reserve.html">予約について</a>
    <a href="https://ssc.doctorqube.com/example/">WEB順番受付はこちら</a>
    <a href="tel:0190000000">電話</a>
    """
    links = find_reservation_links(html, "https://clinic.example.jp/")
    assert links[0] == ("https://ssc.doctorqube.com/example/", "ドクターキューブ")
    assert ("https://clinic.example.jp/reserve.html", "Web予約") in links


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, render=None):
        from pediatrics.fetch import Page
        html = self.pages.get(url)
        return Page(url, url, 200 if html else 404, html or "", None if html else "HTTP 404")


def test_check_clinic_follows_reservation_link():
    f = FakeFetcher({
        "https://c.example/": '<a href="https://x.atlink.jp/c/">順番受付</a>',
        "https://x.atlink.jp/c/": "<p>受付中</p><p>現在 8 番を診察中</p><p>お待ちの方 3人</p>",
    })
    st = check_clinic({"homepage": "https://c.example/"}, f)
    assert st.system == "アットリンク"
    assert st.state == "accepting" and st.waiting == 3


def test_check_clinic_no_site():
    assert check_clinic({"homepage": None}, FakeFetcher({})).state == "no_site"


def test_jsonld_rating():
    html = '<script type="application/ld+json">{"@type":"MedicalClinic","aggregateRating":{"ratingValue":"4.2","reviewCount":"18"}}</script>'
    assert extract_aggregate_rating(html) == (4.2, 18)


def test_text_rating():
    assert extract_aggregate_rating("<div>総合評価 3.85 口コミ 8件</div>") == (3.85, 8)


def test_bayesian_pulls_small_samples_to_prior():
    few, _ = combined_rating([{"rating": 5.0, "count": 1}])
    many, _ = combined_rating([{"rating": 4.5, "count": 100}])
    assert few < many


def test_score_and_now_rank():
    c = {"web_reservation": True, "pediatric_only": True, "saturday": True}
    s = score(c, [{"rating": 4.0, "count": 20}], Status(state="accepting").to_dict())
    assert s["score"] > 80
    a = {"status": {"state": "accepting", "waiting": 2}, "score": 50}
    b = {"status": {"state": "closed", "waiting": None}, "score": 90}
    assert sorted([b, a], key=now_rank_key)[0] is a
