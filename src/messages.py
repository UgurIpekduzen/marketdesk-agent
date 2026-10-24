"""Every Turkish string shown to the end user.

The English ones are in messages_en, under the same names; src.i18n picks
the catalog of a session's language.
"""

# The same sentence for an order that does not exist and for one that
# belongs to another customer.
ORDER_NOT_FOUND = "Bu numarayla size ait bir sipariş bulunamadı."

INVALID_ORDER_STATUS = "Geçersiz sipariş durumu. Geçerli değerler: {allowed}."
INVALID_RETURN_REASON = "Geçersiz iade nedeni. Geçerli değerler: {allowed}."
RETURN_REASON_REQUIRED = (
    "İade nedeni belirtilmedi. Müşteriye siparişi neden iade etmek istediğini sorun."
)

INVALID_AMOUNT = "Geçersiz iade tutarı."
AMOUNT_MISMATCH = "İade tutarı, bu sipariş için hesaplanan tutarla uyuşmuyor."
RETURN_NOT_POSSIBLE = "Bu sipariş için şu anda iade talebi açılamıyor."
DUPLICATE_REQUEST = (
    "Bu sipariş için daha önce bir iade talebi açılmış; ikinci bir talep açılamaz."
)
APPROVAL_REQUIRED = (
    "İade talebi ancak sizin onayınızla oluşturulur. Henüz hiçbir kayıt açılmadı."
)
RETURN_REQUEST_CREATED = "İade talebiniz oluşturuldu."

INVALID_PRIORITY = "Geçersiz öncelik. Geçerli değerler: {allowed}."
EMPTY_SUMMARY = "Devir özeti boş olamaz."
ESCALATED = "Konu bir müşteri temsilcisine iletildi."

UNKNOWN_METRIC = "Böyle bir metrik tanımlı değil. Tanımlı metrikler: {allowed}."
INVALID_DIMENSION = (
    "Bu metrik {name} boyutuna göre kırılamaz. İzinli boyutlar: {allowed}."
)
TOO_MANY_DIMENSIONS = "Bir metrik en fazla {limit} farklı boyuta göre kırılabilir."
ITEM_DIMENSIONS_TOGETHER = (
    "Bu metrik {names} boyutlarına aynı anda kırılamaz: aynı sipariş birden "
    "fazla kez sayılır. Boyutlardan birini seçin."
)
INVALID_METRIC_FILTER = (
    "Bu metrik {name} ile filtrelenemez. İzinli filtreler: {allowed}."
)
INVALID_FILTER_VALUE = (
    "{name} filtresinin değeri bir metin ya da metin listesi olmalıdır."
)
INVALID_PERIOD_FILTER = "{name} filtresi YYYY-AA-GG biçiminde bir tarih olmalıdır."
INVALID_RANKING = (
    "Sıralama seçenekleri geçersiz: order 'value_desc' ya da 'value_asc', "
    "top ve min_count pozitif tam sayı olmalıdır."
)

SQL_REJECTED = {
    "EMPTY_QUERY": "Sorgu boş.",
    "PARSE_ERROR": "Sorgu ayrıştırılamadı; SQL yazımını kontrol edin.",
    "MULTIPLE_STATEMENTS": "Tek seferde yalnızca bir SQL ifadesi çalıştırılabilir.",
    "NOT_A_SELECT": "Yalnızca SELECT sorguları çalıştırılabilir.",
    "FORBIDDEN_STATEMENT": (
        "Sorgu izin verilmeyen bir ifade içeriyor; yalnızca veri okunabilir."
    ),
    "TABLE_NOT_ALLOWED": (
        "Sorgu izin verilmeyen bir tabloya erişiyor. İzinli görünümler: {allowed}."
    ),
    "FUNCTION_NOT_ALLOWED": "Sorgu izin verilmeyen bir fonksiyon çağırıyor.",
    "JOIN_FANS_OUT": (
        "v_order_items ve v_order_payments aynı sorguda birleştirilemez: her ödeme "
        "satırı kalemleri tekrar eder ve toplamlar şişer. Ödemeye göre süzmek için "
        "order_key IN (SELECT order_key FROM v_order_payments WHERE ...) kullanın; "
        "sipariş başına değer için önce kalemleri sipariş başına toplayın."
    ),
}
SQL_ERROR = "Sorgu çalıştırılamadı."
SQL_RESULT_TOO_LARGE = (
    "Sorgunun sonucu çok büyük; yalnızca gereken sütunları ve daha az satırı isteyin."
)
SQL_TIMEOUT = "Sorgu {seconds} saniyede tamamlanmadığı için durduruldu."

# The strings named here reach only the model, inside a tool result; the
# model writes its own answer from them. They stay Turkish whatever the page's
# language, so a Turkish conversation sends the model exactly what it did,
# and they have no English version.
MODEL_ONLY = frozenset(
    {
        "ORDER_NOT_FOUND",
        "INVALID_ORDER_STATUS",
        "INVALID_RETURN_REASON",
        "RETURN_REASON_REQUIRED",
        "INVALID_AMOUNT",
        "AMOUNT_MISMATCH",
        "RETURN_NOT_POSSIBLE",
        "DUPLICATE_REQUEST",
        "APPROVAL_REQUIRED",
        "RETURN_REQUEST_CREATED",
        "INVALID_PRIORITY",
        "EMPTY_SUMMARY",
        "ESCALATED",
        "UNKNOWN_METRIC",
        "INVALID_DIMENSION",
        "TOO_MANY_DIMENSIONS",
        "ITEM_DIMENSIONS_TOGETHER",
        "INVALID_METRIC_FILTER",
        "INVALID_FILTER_VALUE",
        "INVALID_PERIOD_FILTER",
        "INVALID_RANKING",
        "SQL_REJECTED",
        "SQL_ERROR",
        "SQL_RESULT_TOO_LARGE",
        "SQL_TIMEOUT",
        "EMPTY_POLICY_QUERY",
        "CRITIC_CORRECTION",
        "CRITIC_CORRECTION_COMPUTE",
    }
)

# How a policy section is cited in an answer.
POLICY_CITATION = "{document}, Bölüm {number}"
# The documents' own titles are Turkish and are cited as written.
POLICY_DOCUMENT_TITLES: dict[str, str] = {}
EMPTY_POLICY_QUERY = "Arama metni boş olamaz."

# --- Support agent ------------------------------------------------------

STEP_LIMIT_REACHED = (
    "İsteğinizi bu adımda tamamlayamadım. Sorunuzu biraz daha açık yazabilir "
    "ya da konunun bir müşteri temsilcisine aktarılmasını isteyebilirsiniz."
)
EMPTY_REPLY = "Şu anda bir cevap oluşturamadım. Lütfen sorunuzu yeniden yazın."

# The critic of the operations agent. The correction request goes to the
# model, so it is model-only; the note is shown under an answer whose
# numbers could not all be traced to a tool's output.
CRITIC_CORRECTION = (
    "Cevabındaki şu sayılar araçların sonuçlarında yok: {numbers}. Cevabı "
    "yeniden yaz ve yalnızca araçların döndürdüğü sayıları kullan. Gerekli bir "
    "değer sonuçlarda yoksa onu bir araçla getir; getiremiyorsan sayıyı "
    "yazma, bunu söyle."
)
# The wording in use (config.CRITIC_DEFAULT_VARIANT): a derived value is to
# be computed with a query instead of left out. CRITIC_CORRECTION above is the
# first wording, kept to measure against.
CRITIC_CORRECTION_COMPUTE = (
    "Cevabındaki şu sayılar araçların sonuçlarında yok: {numbers}. Cevabı "
    "yeniden yaz ve yalnızca araçların döndürdüğü sayıları kullan. Toplam, "
    "fark, oran ya da ortalama gibi hesaplanmış bir değer gerekiyorsa onu "
    "run_sql ile hesapla; hesaplayamıyorsan sayıyı yazma, bunu söyle."
)
CRITIC_NOTE = (
    "Not: cevaptaki bazı sayılar bu sorgunun sonuçlarında bulunamadı. "
    "Kullanmadan önce kontrol edin."
)

RETURN_REASON_LABELS = {
    "changed_mind": "vazgeçme",
    "late": "geç teslim",
    "damaged": "hasarlı ürün",
    "wrong_item": "yanlış ürün",
}
REQUEST_STATUS_LABELS = {
    "PENDING_REVIEW": "inceleme bekliyor",
    "PENDING_SENIOR": "kıdemli onay bekliyor",
    "APPROVED": "onaylandı",
    "REJECTED": "reddedildi",
}
# A money amount, already written the reader's way, with its currency.
MONEY = "{amount} BRL"
APPROVAL_SUMMARY = (
    "Oluşturulacak iade talebi:\n"
    "  Sipariş: {order}\n"
    "  İade nedeni: {reason}\n"
    "  İade tutarı: {amount}\n"
    "  Talep şu durumda açılacak: {status}"
)
APPROVAL_QUESTION = "Onaylıyor musunuz? [e/h] "
RETURN_REQUEST_CREATED_DETAIL = (
    "İade talebiniz oluşturuldu. Talep numarası: {request_id}, durum: {status}. "
    "Talebiniz bir müşteri temsilcisi tarafından incelenecektir."
)
RETURN_REQUEST_NOT_CREATED = "İade talebi oluşturulmadı: {reason}"
STALE_CARD = (
    "Ekrandaki talep artık bekleyen talep değil; hiçbir iade talebi oluşturulmadı. "
    "Lütfen isteğinizi yeniden yazın."
)
NOTHING_PENDING = "Onay bekleyen bir iade talebi yok."
APPROVAL_DECLINED = "Onay vermediniz; iade talebi oluşturulmadı."

# --- Chat command -------------------------------------------------------

CHAT_BANNER = "MarketDesk müşteri desteği. Çıkmak için 'çık' yazın.\nSorunuzu yazın:"
CHAT_PROMPT = "> "
CHAT_GOODBYE = "Görüşmek üzere."
CHAT_UNKNOWN_CUSTOMER = "Bu müşteri için kayıtlı sipariş bulunamadı."

# --- Ops data agent -----------------------------------------------------

SQL_GAVE_UP = (
    "Bu soruyu cevaplayamadım: denediğim sorgular çalışmadı ve izin verilen "
    "düzeltme sayısı doldu."
)
OPS_USED_SQL_HEADING = "Kullanılan SQL:"
OPS_TRIED_SQL_HEADING = "Denenen SQL:"
OPS_CAVEAT_HEADING = "Not:"

# --- Review Insight Agent -----------------------------------------------

REVIEW_TABLE_COLUMNS = {
    "theme": "Tema",
    "reviews": "Yorum",
    "share": "Pay (%)",
    "quote": "Örnek alıntı",
}
REVIEW_CAVEAT = (
    "Bu bir örneklemdir: eşleşen {matching} yorumdan {sampled} tanesi okundu. "
    "Bir temanın sayısı, sözcüklerinden en az birini içeren yorumların "
    "sayısıdır; gözlemsel bir sayıdır, neden-sonuç değildir."
)
REVIEW_LEFT_OUT = "Kişisel veri kalıbı taşıyan {count} yorum örnekleme alınmadı."
REVIEW_NOT_VERIFIED = (
    "Yorumlardan doğrulanmış temalar çıkaramadım, bu yüzden bir sayı ya da "
    "alıntı vermiyorum. Soruyu kategori, puan ya da dönemle daraltarak "
    "yeniden deneyebilirsiniz."
)
CHAT_BANNER_OPS = (
    "MarketDesk operasyon verileri. Çıkmak için 'çık' yazın.\nSorunuzu yazın:"
)

# --- Router -------------------------------------------------------------

ROUTER_OPS_NOT_ALLOWED = (
    "Bu bilgi müşteri hesabından görüntülenemez. Kendi siparişleriniz, "
    "iadeler, kargo, ödemeler ve politikalarla ilgili sorularınızda yardımcı "
    "olabilirim."
)
ROUTER_SUPPORT_NOT_ALLOWED = (
    "Operasyon oturumunda müşteri destek işlemleri yapılamaz. Operasyon "
    "verileriyle ilgili sorularınızı yanıtlayabilirim."
)
ROUTER_OUT_OF_SCOPE_CUSTOMER = (
    "Bu konuda yardımcı olamıyorum. Siparişleriniz, iadeler, kargo, ödemeler "
    "ve politikalarla ilgili sorularınızı yanıtlayabilirim."
)
ROUTER_OUT_OF_SCOPE_OPS = (
    "Bu konuda yardımcı olamıyorum. Yalnızca operasyon verileriyle ilgili "
    "soruları yanıtlayabilirim."
)

# --- User interface -----------------------------------------------------

UI_TITLE = "MarketDesk"
UI_CAPTION_CUSTOMER = "Müşteri desteği: siparişler, iadeler ve politikalar"
UI_CAPTION_OPS = "Operasyon verileri: metrikler ve sorgular"
UI_SESSION_HEADING = "Oturum"
UI_SESSION_CUSTOMER = "Müşteri"
UI_SESSION_OPS = "Operasyon"
UI_CUSTOMER_PICKER = "Bir durum seçin"
# The choice screen shown before a conversation starts. No sign-in: the
# visitor picks a role and, as a customer, a demo customer's situation.
UI_CHOICE_HEADING = "Nasıl denemek istersiniz?"
UI_CHOICE_NOTE = (
    "Giriş yok ve kişisel veri alınmaz. Örnek müşteriler ve demo verisi bütün "
    "ziyaretçiler için ortaktır."
)
UI_CHOICE_CUSTOMER = "Müşteri olarak"
UI_CHOICE_CUSTOMER_TEXT = "Siparişlerinizi, iade haklarınızı ve politikaları sorun."
UI_CHOICE_OPS = "Operasyon ekibi olarak"
UI_CHOICE_OPS_TEXT = (
    "Metrik sorularını sayılarla yanıtlar; kullanılan SQL'i gösterir. Veriler "
    "yalnızca okunur."
)
UI_START_CUSTOMER = "Müşteri olarak başla"
UI_START_OPS = "Operasyon olarak başla"
UI_CHOICE_REP = "Destek temsilcisi olarak"
UI_CHOICE_REP_TEXT = (
    "Müşteri asistanının açtığı iade taleplerini ve destek biletlerini "
    "inceleyin; kararı siz verirsiniz."
)
UI_START_REP = "Temsilci olarak başla"
UI_SESSION_REP = "Destek temsilcisi"
UI_REFRESH = "Yenile"
UI_CHANGE = "Değiştir"
UI_EXAMPLES_HEADING = "Örnek sorular"
UI_NEW_CONVERSATION = "Yeni konuşma"
UI_INPUT_CUSTOMER = "Sorunuzu yazın"
UI_INPUT_OPS = "Bir metrik sorusu yazın"
UI_INPUT_WAITING_APPROVAL = "Önce aşağıdaki talebi onaylayın ya da vazgeçin"
UI_THINKING = "Yanıt hazırlanıyor..."
UI_IMAGE_REMOVED = "[resim kaldırıldı]"
UI_DEVELOPER_DETAILS = "Geliştirici ayrıntıları"
UI_STEPS_LATEST = "Son cevabın adımları"
UI_STEPS_AGENT = "Yanıtlayan"
UI_STEPS_TOOLS = "Çağrılan araçlar"
UI_STEPS_NO_TOOLS = "yok"
UI_STEPS_COUNTS = "{steps} adım, {tokens} token"
UI_AGENT_SUPPORT = "Destek ajanı"
UI_AGENT_OPS = "Operasyon veri ajanı"
UI_AGENT_REVIEWS = "Yorum içgörü ajanı"
UI_AGENT_ROUTER = "Yönlendirici (istek bu oturumda yanıtlanmadı)"
UI_RESULT_TABLE = "Sonuç"
# Column headers of a result table, for the dimensions of the semantic
# layer and the columns every metric result has; any other column (from
# free SQL) keeps its own name.
UI_TABLE_DIMENSIONS = {
    "purchase_month": "Ay",
    "customer_state": "Müşteri eyaleti",
    "seller_state": "Satıcı eyaleti",
    "seller_key": "Satıcı",
    "product_category_en": "Kategori",
}
UI_COLUMN_NUMERATOR = "Pay"
UI_COLUMN_DENOMINATOR = "Payda"
UI_COLUMN_VALUE = "Değer"
# Under a result written as text, when rows were left out.
TABLE_ROWS_LEFT_OUT = "... ve {count} satır daha"
UI_SOURCES = "Kaynak"

# The seller report on the operations page.
UI_SELLER_REPORT = "Satıcı raporu"
UI_SELLER_REPORT_SHOW = "Raporu hazırla"
UI_SELLER_REPORT_INTRO = (
    "Kargoya geç veren satıcılar, en yüksek orandan başlayarak. En az {items} kalemi "
    "olan satıcılar sıralanır; ilk {rows} satıcı gösterilir. Satıcılar takma adla "
    "gösterilir, gerçek satıcı kimliği hiçbir yerde yer almaz."
)
UI_SELLER_REPORT_EMPTY = "Bu koşullarda eşiği geçen satıcı yok."
UI_SELLER_REPORT_SOURCES = "Her sayının kaynağı"
SELLER_REPORT_COLUMNS = {
    "seller": "Satıcı",
    "items": "Kalem",
    "late_rate": "Geç kargo oranı (%)",
    "orders": "Sipariş",
    "gmv": "GMV (BRL)",
    "avg_review_score": "Ort. yorum puanı",
}
UI_APPROVAL_HEADING = "Onayınız gerekiyor"
UI_APPROVAL_ORDER = "Sipariş"
UI_APPROVAL_REASON = "İade nedeni"
UI_APPROVAL_AMOUNT = "İade tutarı"
UI_APPROVAL_LEVEL = "Talep şu durumda açılacak"
UI_APPROVE = "Onayla"
UI_DECLINE = "Vazgeç"
UI_PREPARING_DATABASE = (
    "Demo verisi hazırlanıyor: veri seti indirilip veritabanı kuruluyor. "
    "Bu yalnızca uygulamanın ilk açılışında olur ve bir iki dakika sürebilir."
)
UI_PAUSED = "Sayfa şu anda bakımda. Lütfen biraz sonra tekrar deneyin."
UI_NO_DATABASE = (
    "Demo verisi hazırlanamadı. Lütfen sayfayı birkaç dakika sonra yenileyin; "
    "yerelde veritabanı `task data` komutuyla hazırlanır."
)
# A credit line in the usual English form, like the dataset's name and
# licence: an exception to the Turkish interface chosen by the author.
UI_DATA_NOTE = "Data: Olist Brazilian E-Commerce, CC BY-NC-SA 4.0"
# The language switch: its label is the same in both languages, so either
# reader finds it.
UI_LANGUAGE_SWITCH = "Dil · Language"
UI_LANGUAGE_HELP = "Dil değişince yeni bir konuşma başlar."
UI_LANGUAGE_CHANGED = (
    "Dil değiştiği için yeni bir konuşma başladı. Önceki konuşmada onay "
    "bekleyen bir talep varsa oluşturulmadı."
)
UI_SESSION_EXPIRED = (
    "Uzun süre işlem yapılmadığı için önceki sohbet kapatıldı; yeni bir sohbet "
    "başlatıldı."
)
UI_ERROR_FULL = (
    "Demo şu an çok sayıda ziyaretçiye hizmet veriyor. Lütfen birkaç dakika "
    'sonra "Yeni sohbet" düğmesiyle tekrar deneyin.'
)
UI_ERROR_TOO_LONG = "Mesajınız çok uzun; lütfen en fazla {limit} karakterle yazın."
UI_ERROR_APPROVAL_WAITING = "Önce ekrandaki iade talebini onaylayın ya da reddedin; sonra yeni mesaj yazabilirsiniz."
UI_ERROR_QUESTION_LIMIT = (
    "Demo şu an çok yoğun: bu saat için soru sınırına ulaşıldı. Lütfen biraz "
    "sonra tekrar deneyin."
)
UI_ERROR_DAILY_BUDGET = (
    "Demo bugünkü soru hakkını doldurdu. Lütfen yarın tekrar deneyin."
)
UI_NO_CUSTOMERS = "Veritabanında örnek müşteri bulunamadı."
UI_ERROR_QUOTA = (
    "Yapay zekâ servisinin ücretsiz kullanım kotası şu an dolmuş görünüyor. "
    "Lütfen bir süre sonra tekrar deneyin."
)
UI_ERROR_BUSY = (
    "Yapay zekâ servisi şu an yoğun ya da yanıt vermiyor. Lütfen biraz sonra "
    "tekrar deneyin."
)
UI_ERROR_TIMEOUT = "Yanıt zamanında gelmedi. Lütfen tekrar deneyin."
UI_ERROR_NOT_CONFIGURED = (
    "Uygulama henüz yapılandırılmamış: yapay zekâ servisinin anahtarı tanımlı değil."
)
UI_ERROR_KEY_REFUSED = (
    "Yapay zekâ servisi uygulamanın anahtarını kabul etmedi; anahtarın "
    "yenilenmesi gerekiyor. Lütfen daha sonra tekrar deneyin."
)
UI_ERROR_GENERIC = (
    "Beklenmeyen bir sorun oluştu ve isteğiniz yanıtlanamadı. Lütfen tekrar deneyin."
)
DEMO_CUSTOMER_LABELS = {
    "recent_delivery": "Siparişi yeni teslim edilmiş müşteri",
    "late_delivery": "Siparişi geç teslim edilmiş müşteri",
    "in_transit": "Siparişi kargoda olan müşteri",
    "window_passed": "İade süresi geçmiş müşteri",
    "many_orders": "Çok siparişi olan müşteri",
}

# Example questions offered above an empty conversation. Each was tried with
# the real model and answered well; none is from the held-out test split.
# Customer questions that need the situation of the demo customer:
EXAMPLE_QUESTIONS_BY_SITUATION = {
    "recent_delivery": [
        "Son siparişimden vazgeçtim, iade etmek istiyorum.",
        "Son siparişim hasarlı geldi, iade talebi açar mısınız?",
    ],
    "late_delivery": ["Son siparişim kaç gün gecikti?"],
    "in_transit": ["Son siparişim nerede, ne zaman gelir?"],
    "window_passed": [
        "Son siparişimi iade etmek istiyorum, vazgeçtim.",
        "Son siparişim hasarlı çıktı, hâlâ iade edebilir miyim?",
    ],
    "many_orders": [
        "Siparişlerimi listeler misin?",
        "En son verdiğim siparişin durumu ne?",
    ],
}
# Customer questions that fit every situation.
EXAMPLE_QUESTIONS_GENERAL = [
    "Son siparişim nerede?",
    "Siparişimle ilgili yardım istiyorum.",
]
# Customer questions answered from the policies.
EXAMPLE_QUESTIONS_POLICY = [
    "Siparişim temin edilemezse param nasıl iade edilir?",
    "Kargoya verilmiş bir siparişi iptal edebilir miyim?",
    "İade süremi kaçırdım, geç teslimat için yine de kargo ücretimi isteyebilir miyim?",
    "Hasarlı ürün için iade talebi nasıl açılır, kim onaylar?",
    "Siparişimin bir kısmını hediye çekiyle ödedim, iade olursa param nasıl geri ödenir?",
    "Henüz kargoya verilmemiş bir sipariş nasıl iptal edilir?",
    "İade edilen para hesabıma kaç günde geçer?",
]
EXAMPLE_QUESTIONS_OPS = [
    "GMV'si en yüksek 5 ürün kategorisi hangileri?",
    "2018 yılında aylara göre ortalama yorum puanı nedir?",
    "En az 300 siparişi olan müşteri eyaletleri arasında iptal oranı en yüksek 5'i hangileri?",
    "2018 yılında aylara göre sipariş sayısı nedir?",
    "2018 Temmuz'da SP eyaletinde geç teslim oranı neydi?",
    "En az 100 siparişi olan kategoriler arasında geç teslim oranı en yüksek 5'i hangileri?",
    "2018 Ağustos ayının GMV'si ne kadar?",
    "En az 500 siparişi olan eyaletler arasında iptal oranı en yüksek 3 eyalet hangisi?",
    "Her ödeme türü kaç farklı siparişte kullanılmış?",
    "2018 yılında SP ve RJ eyaletlerinde aylara göre sipariş sayıları nedir?",
    "Mobilya kategorisinde 1 ve 2 puan veren müşteriler yorumlarında en çok neden şikâyet ediyor?",
    "5 puan veren müşteriler yorumlarında en çok neyi övüyor?",
    "Sağlık ve güzellik kategorisinde müşteriler teslimat hakkında ne yazıyor?",
]

# The support rep's review queue. Decisions on return requests and closing
# tickets are made in code; these are the answers to a refused one.
REVIEW_NOT_FOUND = "Bu numarada bir kayıt bulunamadı."
REVIEW_SENIOR_ONLY = (
    "Bu talep 500 BRL'nin üstünde: kıdemli onayı gerekir, bu ekrandan "
    "onaylanamaz ya da reddedilemez."
)
REVIEW_ALREADY_DECIDED = "Bu talep için zaten karar verilmiş."
REVIEW_TICKET_ALREADY_CLOSED = "Bu bilet zaten kapatılmış."
REVIEW_INVALID_DECISION = "Geçersiz karar."

# The support rep's console.
UI_REVIEW_HEADING = "İnceleme kuyruğu"
UI_REVIEW_NOTE = (
    "Kararları siz verirsiniz; yapay zekâ bu ekranda karar vermez. Bilet "
    "özetlerini yapay zekâ yazdı: kararı talebin kendi bilgileriyle doğrulayın."
)
UI_REVIEW_REQUESTS_TAB = "İade talepleri ({count})"
UI_REVIEW_TICKETS_TAB = "Destek biletleri ({count})"
UI_REVIEW_NO_REQUESTS = "Bekleyen iade talebi yok."
UI_REVIEW_NO_TICKETS = "Açık destek bileti yok."
UI_REVIEW_DECIDED = "Karara bağlananlar (son {count})"
UI_REVIEW_APPROVE = "Onayla"
UI_REVIEW_REJECT = "Reddet"
UI_REVIEW_CLOSE = "Kapat"
UI_REVIEW_SENIOR_NOTE = (
    "500 BRL'nin üstünde: kıdemli onayı gerekir, bu ekrandan karar verilemez."
)
UI_REVIEW_REQUEST_TITLE = "Talep {id} · Sipariş `{order}` · Müşteri `{customer}`"
UI_REVIEW_REQUEST_DETAILS = "{reason} · {amount} · {date} · {status}"
UI_REVIEW_TICKET_TITLE = "{number} · {priority} öncelik · {date} · Müşteri `{customer}`"
UI_REVIEW_DECIDED_DONE = "Talep {id}: {status}."
UI_REVIEW_TICKET_CLOSED = "{number} kapatıldı."
PRIORITY_LABELS = {"low": "düşük", "normal": "normal", "high": "yüksek"}

# "How it was computed": a line under a metric answer, written by code from
# the metric call, not by the model.
COMPUTED_HEADING = "Nasıl hesaplandı"
COMPUTED_GROUP_BY = "kırılım: {dimensions}"
COMPUTED_FILTER = "filtre: {filters}"
COMPUTED_PERIOD_BOTH = "sipariş tarihi {start} – {end}"
COMPUTED_PERIOD_FROM = "sipariş tarihi {start} ve sonrası"
COMPUTED_PERIOD_TO = "sipariş tarihi {end} ve öncesi"
COMPUTED_MIN_COUNT = "en az {count} {unit}"
COMPUTED_UNITS = {"order": "sipariş", "item": "kalem"}
COMPUTED_ORDER = {"value_desc": "değere göre azalan", "value_asc": "değere göre artan"}
COMPUTED_TOP = "ilk {top}"
COMPUTED_REPORT_SELLERS = "yalnızca rapordaki satıcılar için"
COMPUTED_SCOPE = "{today} ve öncesinde verilen siparişler"

# The SQL of the newest answer, opened from the sidebar in a wide window.
UI_SHOW_SQL = "SQL'i göster"
UI_SQL_DIALOG_TITLE = "SQL sorgusu"
