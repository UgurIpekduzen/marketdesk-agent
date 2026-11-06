"""Questions for the retrieval tests, each with the sections that answer it.

One or more questions per rule, and three the policies deliberately do not
answer (rule None): for those the right result is the section that says so.
A section is written as (file name, section number).
"""

QUESTIONS = [
    ("R0", "2018 Eylül'den sonra verdiğim sipariş neden görünmüyor?", [("returns", 1)]),
    ("R1", "Arkadaşımın siparişinin durumunu öğrenebilir miyim?", [("returns", 1)]),
    (
        "R2",
        "Siparişim henüz hazırlanıyor, iptal edebilir miyim?",
        [("cancellation", 1), ("cancellation", 2)],
    ),
    (
        "R3",
        "Siparişim kargoya verildi, iptal edebilir miyim?",
        [("cancellation", 3), ("shipping_and_delays", 1)],
    ),
    (
        "R3",
        "Ürün hâlâ yolda, şimdiden iade talebi açabilir miyim?",
        [("shipping_and_delays", 1), ("cancellation", 3)],
    ),
    (
        "R4",
        "İptal edilen siparişimin parası ne olacak?",
        [("payments_and_refunds", 4), ("cancellation", 4)],
    ),
    (
        "R5",
        "Sipariş teslim edildi görünüyor ama teslim tarihi yok, iade edebilir miyim?",
        [("returns", 4)],
    ),
    ("R6", "Ürünü beğenmedim, kaç gün içinde iade edebilirim?", [("returns", 2)]),
    (
        "R7",
        "Ürün kırık geldi, kaç gün içinde iade edebilirim?",
        [("damaged_or_wrong_item", 2)],
    ),
    (
        "R7",
        "Sipariş ettiğimden farklı bir ürün gönderilmiş",
        [
            ("damaged_or_wrong_item", 1),
            ("damaged_or_wrong_item", 2),
            ("damaged_or_wrong_item", 3),
        ],
    ),
    (
        "R8",
        "İade edersem kargo ücretini de geri alır mıyım?",
        [("returns", 3), ("payments_and_refunds", 1), ("shipping_and_delays", 3)],
    ),
    (
        "R9",
        "Kargo 12 gün geç geldi, kargo ücretimi geri alabilir miyim?",
        [("shipping_and_delays", 3)],
    ),
    (
        "R9",
        "İade sürem geçti ama teslimat çok gecikmişti, bir hakkım var mı?",
        [("shipping_and_delays", 4)],
    ),
    (
        "R10",
        "600 BRL'lik iade talebim neden kıdemli onay bekliyor?",
        [("payments_and_refunds", 2), ("returns", 6)],
    ),
    (
        "R11",
        "Aynı sipariş için ikinci kez iade talebi açabilir miyim?",
        [("returns", 5)],
    ),
    (
        "R12",
        "Hediye çekiyle ödedim, iadem nasıl yapılır?",
        [("payments_and_refunds", 3)],
    ),
    (
        "R13",
        "Satıcı ürünü kargoya geç vermiş, bu durumda ne olur?",
        [("shipping_and_delays", 5)],
    ),
    (None, "Param hesabıma kaç günde geçer?", [("payments_and_refunds", 5)]),
    (None, "İade kargosunun ücretini kim öder?", [("returns", 7)]),
    (None, "Ürünü yenisiyle değiştirebilir miyim?", [("damaged_or_wrong_item", 5)]),
]
