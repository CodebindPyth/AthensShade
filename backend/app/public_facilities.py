"""Athens public-service premises checked against published service addresses.

The map coordinates identify the premises for an atlas lookup. They carry no
placement or works approval. OSM data © OpenStreetMap contributors (ODbL).
"""

from dataclasses import dataclass

from .models import Source


@dataclass(frozen=True)
class PublicFacility:
    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    coordinates_url: str
    kind: str
    agency: str
    source: Source

    @property
    def notes(self) -> tuple[str, ...]:
        return OPTIONS[self.kind]


OPTIONS = {
    "police": (
        "Εξέτασε σκίαση του χώρου αναμονής σε συνεργασία με την Ελληνική Αστυνομία και με ελεύθερη κάθε υπηρεσιακή δίοδο.",
        "Φύτευση ή ανεξάρτητο πλέγμα σε επιτρεπόμενο προαύλιο, μετά από αυτοψία του φορέα.",
    ),
    "fire": (
        "Εξέτασε σκίαση σε καθορισμένο χώρο πεζών, με εντελώς ελεύθερες τις εξόδους και τις οδεύσεις οχημάτων.",
        "Φυτεμένο δώμα μόνο μετά από έλεγχο του φορέα για φορτία, στεγάνωση, άρδευση και συντήρηση.",
    ),
    "hospital": (
        "Εξέτασε σκίαση σε εξωτερικούς χώρους αναμονής, με ελεύθερες τις ράμπες, τις οδεύσεις ασθενών και την πρόσβαση ασθενοφόρων.",
        "Φύτευση σε κατάλληλη αυλή ή φυτεμένο δώμα ύστερα από τεχνικό έλεγχο της διοίκησης του νοσοκομείου.",
    ),
    "kep": (
        "Εξέτασε σκίαση στον εξωτερικό χώρο αναμονής του ΚΕΠ με ελεύθερη τη ράμπα και την προσβάσιμη είσοδο.",
        "Αναρριχώμενα σε ανεξάρτητο πλέγμα ή φύτευση της αυλής όπου υπάρχει κατάλληλος χώρος και άρδευση.",
    ),
    "court": (
        "Εξέτασε σκίαση στον εξωτερικό χώρο αναμονής, μετά από έγκριση της δικαστικής υπηρεσίας και έλεγχο των οδεύσεων.",
        "Δέντρα σε κατάλληλο προαύλιο ή φυτεμένο δώμα, μόνο ύστερα από τεχνική μελέτη και έγκριση του φορέα.",
    ),
}


def _source(id_: str, title: str, url: str) -> Source:
    return Source(id=id_, title=title, url=url, period="Δημοσιευμένη διεύθυνση υπηρεσίας", kind="public_facilities")


POLICE = _source(
    "athens-police-directory", "Ελληνική Αστυνομία · Διεύθυνση Αστυνομίας Αθηνών",
    "https://www.astynomia.gr/epikoinonia/g-a-d-attikis/diefthynsi-astynomias-athinon/",
)
TRAFFIC_POLICE = _source(
    "athens-traffic-police", "Ελληνική Αστυνομία · Τροχαία Αττικής",
    "https://www.astynomia.gr/anazitisi-ypiresion/nomos-attikis/",
)
FIRE_TWO = _source(
    "athens-fire-station-2", "Πυροσβεστικό Σώμα · 2ος Πυροσβεστικός Σταθμός Αθηνών",
    "https://www.fireservice.gr/documents/20184/3370634/dihgima_seyxaristw%2Bellhna_nikolaou%2Bpipilh.pdf/6f3ed66c-b3d7-4af9-90c3-16172a042f67",
)
FIRE_DIRECTORATE = _source(
    "athens-fire-directorate", "Πυροσβεστικό Σώμα · Κατάλογος υπηρεσιών",
    "https://www.fireservice.gr/katataxi/emode/doc/f1057df6-8c3f-40c2-867a-da75831f3eab.pdf",
)
FIRE_HISTORIC = _source(
    "athens-fire-historic-building", "Πυροσβεστικό Σώμα · Ιστορικό Αρχηγείο",
    "https://www.fireservice.gr/en_US/-/eortasmos-ethnikes-epeteiou-25es-martiou-1821",
)
HOSPITALS = _source(
    "athens-health-service-directory", "1η Υγειονομική Περιφέρεια Αττικής · Νοσοκομεία",
    "https://www.1dype.gov.gr/εσυ/νοσοκομεία/",
)
TRIAL_COURTS = _source(
    "athens-court-directory", "Υπουργείο Δικαιοσύνης · Κατάλογος Πρωτοδικείων",
    "https://ministryofjustice.gr/wp-content/uploads/2026/03/Protodikeia_31032026.pdf",
)
COURT_DEGLERI = _source(
    "athens-court-degleri", "Υπουργείο Δικαιοσύνης · Διευθύνσεις Πρωτοδικείου Αθηνών",
    "https://ministryofjustice.gr/wp-content/uploads/2025/05/Protodikeia_26052025.pdf",
)
APPEALS = _source(
    "athens-appeals-court", "Εισαγγελία Εφετών Αθηνών · Διεύθυνση",
    "https://prosec.gov.gr/",
)
KEP_SEPOLIA = _source(
    "athens-kep-sepolia", "Δήμος Αθηναίων · ΚΕΠ Σεπολίων", "https://www.cityofathens.gr/place/4o-kep-sepolia/",
)
KEP_PETRALONA = _source(
    "athens-kep-petralona", "Δήμος Αθηναίων · ΚΕΠ Πετραλώνων", "https://www.cityofathens.gr/place/3o-kep-petralona/",
)
KEP_NEOS_KOSMOS = _source(
    "athens-kep-neos-kosmos", "Δήμος Αθηναίων · ΚΕΠ Νέου Κόσμου", "https://www.cityofathens.gr/place/2o-kep-n-kosmos/",
)
KEP_DIRECTORY = _source(
    "athens-kep-directory", "Δήμος Αθηναίων · Κέντρα Εξυπηρέτησης Πολιτών",
    "https://old.cityofathens.gr/katoikoi/eksypiretisi-politi/k-e-p/stoixeia-epikoinonias-me-kep",
)
KEP_AMERIKIS = _source(
    "athens-kep-amerikis", "Δήμος Αθηναίων · ΚΕΠ Πλατείας Αμερικής", "https://www.cityofathens.gr/place/kep-plateia-amerikis/",
)

AGENCIES = {
    "police": "Ελληνική Αστυνομία",
    "fire": "Πυροσβεστικό Σώμα",
    "hospital": "1η Υγειονομική Περιφέρεια Αττικής",
    "kep": "Δήμος Αθηναίων",
    "court": "Υπουργείο Δικαιοσύνης",
}


def _facility(
    kind: str,
    id_: str,
    name: str,
    address: str,
    latitude: float,
    longitude: float,
    coordinates_reference: str,
    source: Source,
) -> PublicFacility:
    coordinates_url = coordinates_reference if coordinates_reference.startswith("https://") else (
        f"https://www.openstreetmap.org/{coordinates_reference}"
    )
    return PublicFacility(f"public-{kind}-{id_}", name, address, latitude, longitude, coordinates_url, kind, AGENCIES[kind], source)


PUBLIC_FACILITIES = (
    _facility("police", "syntagmatos", "Αστυνομικό Τμήμα Συντάγματος", "Μιμνέρμου 6–8",
              37.9721602, 23.7419699, "node/519860120", POLICE),
    _facility("police", "omonoia", "Αστυνομικό Τμήμα Ομονοίας", "Βερανζέρου 24",
              37.9858136, 23.7278033, "way/447974916", POLICE),
    _facility("police", "acropolis", "Αστυνομικό Τμήμα Ακροπόλεως", "Λεωφόρος Συγγρού 83",
              37.9607509, 23.7223972, "node/10798990936", POLICE),
    _facility("police", "ampelokipoi", "Αστυνομικό Τμήμα Αμπελοκήπων", "Σεβαστουπόλεως 14",
              37.9868929, 23.7635354, "node/2502436884", POLICE),
    _facility("police", "exarcheia", "Αστυνομικό Τμήμα Εξαρχείων", "Καλλιδρομίου 12",
              37.9852539, 23.7395109, "node/1613229388", POLICE),
    _facility("police", "kolonos", "Αστυνομικό Τμήμα Κολωνού", "Λαοδάμαντος 1–3",
              38.0002578, 23.7175746, "node/613126663", POLICE),
    _facility("police", "kypseli", "Αστυνομικό Τμήμα Κυψέλης", "Θήρας 17",
              38.0012492, 23.7343356, "way/471649258", POLICE),
    _facility("police", "patisia", "Αστυνομικό Τμήμα Πατησίων", "Αγίας Λαύρας 17",
              38.0171081, 23.7391351, "way/501802217", POLICE),
    _facility("police", "pagkrati", "Αστυνομικό Τμήμα Παγκρατίου", "Πρατίνου 49",
              37.9706754, 23.7481617, "node/6805829069", POLICE),
    _facility("police", "agios-panteleimonas", "Αστυνομικό Τμήμα Αγίου Παντελεήμονα", "Μιχαήλ Βόδα 85",
              37.9961576, 23.7253492, "node/1434326599", POLICE),
    _facility("police", "traffic-athens", "Τροχαία Αθηνών", "Θεόδωρου Δηληγιάννη 24–26",
              37.9877522, 23.7203642, "way/454059159", TRAFFIC_POLICE),
    _facility("fire", "station-2", "2ος Πυροσβεστικός Σταθμός Αθηνών", "Μαραθωνομάχων 49",
              37.9886932, 23.7092253, "relation/7567311", FIRE_TWO),
    _facility("fire", "directorate", "Διοίκηση Πυροσβεστικών Υπηρεσιών Αθηνών", "Παναγή Τσαλδάρη 31",
              37.982259, 23.7243646, "way/449517798", FIRE_DIRECTORATE),
    _facility("fire", "historic-hq", "Ιστορικό Αρχηγείο Πυροσβεστικού Σώματος", "Μουρούζη 4",
              37.9746785, 23.7415749, "way/219192471", FIRE_HISTORIC),
    _facility("hospital", "polyclinic", "Πολυκλινική Αθηνών", "Πειραιώς 3",
              37.9832852, 23.7268262, "way/439961403", HOSPITALS),
    _facility("hospital", "agia-sofia", "Νοσοκομείο Παίδων «Η Αγία Σοφία»", "Θηβών και Παπαδιαμαντοπούλου",
              37.985387, 23.7689617, "relation/3557351", HOSPITALS),
    _facility("hospital", "kyriakou", "Νοσοκομείο Παίδων «Π. και Α. Κυριακού»", "Θηβών και Λεβαδείας",
              37.9852654, 23.7679647, "way/208617853", HOSPITALS),
    _facility("hospital", "erythros-stavros", "Κοργιαλένειο–Μπενάκειο Νοσοκομείο", "Αθανασάκη 2",
              37.9920649, 23.769252, "relation/3419290", HOSPITALS),
    _facility("hospital", "evangelismos", "Νοσοκομείο «Ο Ευαγγελισμός»", "Υψηλάντου 45–47",
              37.9777601, 23.7477793, "way/132620005", HOSPITALS),
    _facility("hospital", "alexandra", "Νοσοκομείο «Αλεξάνδρα»", "Λεωφόρος Βασιλίσσης Σοφίας 80",
              37.9801307, 23.7552795, "way/132748278", HOSPITALS),
    _facility("hospital", "syggros", "Νοσοκομείο «Ανδρέας Συγγρός»", "Ίωνος Δραγούμη 5",
              37.9734795, 23.7523067, "way/132756187", HOSPITALS),
    _facility("hospital", "ippokrateio", "Νοσοκομείο «Ιπποκράτειο»", "Λεωφόρος Βασιλίσσης Σοφίας 114",
              37.9836922, 23.7597588, "way/132795203", HOSPITALS),
    _facility("hospital", "elpis", "Νοσοκομείο «Η Ελπίς»", "Δημητσάνας 7",
              37.9899876, 23.7553889, "way/140757110", HOSPITALS),
    _facility("hospital", "laiko", "Νοσοκομείο «Λαϊκό»", "Αγίου Θωμά 17",
              37.9840353, 23.7652256, "way/169296315", HOSPITALS),
    _facility("hospital", "gennimatas", "Νοσοκομείο «Γ. Γεννηματάς»", "Λεωφόρος Μεσογείων 154",
              37.9967836, 23.7838188, "way/208978514", HOSPITALS),
    _facility("hospital", "sotiria", "Νοσοκομείο «Η Σωτηρία»", "Λεωφόρος Μεσογείων 152",
              37.9937980, 23.7835000, "way/316732250", HOSPITALS),
    _facility("hospital", "pammakaristos", "Νοσοκομείο «Η Παμμακάριστος»", "Ιακωβάτων 43",
              38.0142613, 23.7315822, "way/505569755", HOSPITALS),
    _facility("kep", "neos-kosmos", "ΚΕΠ Νέου Κόσμου", "Φρειδερίκου Σμιθ και Πλατεία Μπλόκου Δουργούτι",
              37.956994, 23.721683, str(KEP_NEOS_KOSMOS.url), KEP_NEOS_KOSMOS),
    _facility("kep", "sepolia", "ΚΕΠ Σεπολίων", "Αυλώνος 26–28",
              38.0034121, 23.7195666, "node/5836508425", KEP_SEPOLIA),
    _facility("kep", "petralona", "ΚΕΠ Πετραλώνων", "Κειριαδών 70",
              37.9706306, 23.7090344, "node/11614902055", KEP_PETRALONA),
    _facility("kep", "akadimias", "ΚΕΠ Ακαδημίας", "Ακαδημίας 88",
              37.9846412, 23.7320595, "node/11614901739", KEP_DIRECTORY),
    _facility("kep", "patisia", "ΚΕΠ Πατησίων", "Αγίας Λαύρας 24",
              38.0177514, 23.7399119, "node/11614902116", KEP_DIRECTORY),
    _facility("kep", "ampelokipoi", "ΚΕΠ Αμπελοκήπων", "Λουίζης Ριανκούρ 71",
              37.9936331, 23.7645626, "node/4500378994", KEP_DIRECTORY),
    _facility("kep", "amerikis", "ΚΕΠ Πλατείας Αμερικής", "Πατησίων 159",
              38.0010715, 23.7334345, "node/12431096265", KEP_AMERIKIS),
    _facility("court", "degleri", "Πρωτοδικείο Αθηνών – Κτίριο Δέγλερη", "Δέγλερη 4",
              37.9899191, 23.7538106, "node/6078671483", COURT_DEGLERI),
    _facility("court", "evelpidon", "Πρωτοδικείο Αθηνών – Πρώην Σχολή Ευελπίδων", "Ευελπίδων",
              37.9953907, 23.7433996, "way/49431011", TRIAL_COURTS),
    _facility("court", "appeals", "Εφετείο Αθηνών", "Κυρίλλου Λουκάρεως 14",
              37.9890632, 23.7530214, "relation/6614266", APPEALS),
)
