"""Every Turkish string shown to the end user."""

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
}
SQL_ERROR = "Sorgu çalıştırılamadı."
SQL_TIMEOUT = "Sorgu {seconds} saniyede tamamlanmadığı için durduruldu."

# How a policy section is cited in an answer.
POLICY_CITATION = "{document}, Bölüm {number}"
EMPTY_POLICY_QUERY = "Arama metni boş olamaz."

# --- Support agent ------------------------------------------------------

STEP_LIMIT_REACHED = (
    "İsteğinizi bu adımda tamamlayamadım. Sorunuzu biraz daha açık yazabilir "
    "ya da konunun bir müşteri temsilcisine aktarılmasını isteyebilirsiniz."
)
EMPTY_REPLY = "Şu anda bir cevap oluşturamadım. Lütfen sorunuzu yeniden yazın."

RETURN_REASON_LABELS = {
    "changed_mind": "vazgeçme",
    "late": "geç teslim",
    "damaged": "hasarlı ürün",
    "wrong_item": "yanlış ürün",
}
REQUEST_STATUS_LABELS = {
    "PENDING_REVIEW": "inceleme bekliyor",
    "PENDING_SENIOR": "kıdemli onay bekliyor",
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
UI_CUSTOMER_PICKER = "Örnek müşteri"
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
UI_AGENT_ROUTER = "Yönlendirici (istek bu oturumda yanıtlanmadı)"
UI_RESULT_TABLE = "Sonuç"
# Column headers of a result table, for the dimensions of the semantic
# layer and the columns every metric result has; any other column (from
# free SQL) keeps its own name.
UI_TABLE_DIMENSIONS = {
    "purchase_month": "Ay",
    "customer_state": "Müşteri eyaleti",
    "seller_state": "Satıcı eyaleti",
    "product_category_en": "Kategori",
}
UI_COLUMN_NUMERATOR = "Pay"
UI_COLUMN_DENOMINATOR = "Payda"
UI_COLUMN_VALUE = "Değer"
# Under a result written as text, when rows were left out.
TABLE_ROWS_LEFT_OUT = "... ve {count} satır daha"
UI_SOURCES = "Kaynak"
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
UI_NO_DATABASE = (
    "Demo verisi hazırlanamadı. Lütfen sayfayı birkaç dakika sonra yenileyin; "
    "yerelde veritabanı `task data` komutuyla hazırlanır."
)
# A credit line in the usual English form, like the dataset's name and
# licence: an exception to the Turkish interface chosen by the author.
UI_DATA_NOTE = "Data: Olist Brazilian E-Commerce, CC BY-NC-SA 4.0"
UI_SESSION_EXPIRED = (
    "Uzun süre işlem yapılmadığı için önceki sohbet kapatıldı; yeni bir sohbet "
    "başlatıldı."
)
UI_ERROR_FULL = (
    "Demo şu an çok sayıda ziyaretçiye hizmet veriyor. Lütfen birkaç dakika "
    'sonra "Yeni sohbet" düğmesiyle tekrar deneyin.'
)
UI_ERROR_TOO_LONG = "Mesajınız çok uzun; lütfen en fazla {limit} karakterle yazın."
UI_ERROR_QUESTION_LIMIT = (
    "Demo şu an çok yoğun: bu saat için soru sınırına ulaşıldı. Lütfen biraz "
    "sonra tekrar deneyin."
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
]
