from .models import MethodologyIndicator, MethodologyReference, MethodologyResponse, MonitoringStage


def methodology() -> MethodologyResponse:
    return MethodologyResponse(
        priority_order=[
            "Περισσότερα σημεία στη θερμότερη ζώνη με έλλειψη δενδροκάλυψης ή τεκμηριωμένη έλλειψη σκίασης.",
            "Μεγαλύτερο άθροισμα διαθέσιμων τιμών πληθυσμιακής πυκνότητας σε αυτά τα σημεία.",
            "Στη στρατηγική άμεσης σκίασης, μεγαλύτερο άθροισμα των κατώτερων εκτιμήσεων σκιάς μετά την εγκατάσταση.",
            "Περισσότερο εκτιμώμενο όφελος του μοντέλου και, σε ισοβαθμία, μικρότερο κόστος.",
        ],
        population_exposure_note=(
            "Ο δείκτης έκθεσης αθροίζει τις διαθέσιμες εκτιμήσεις πυκνότητας γύρω από τα σημεία υψηλής προτεραιότητας. "
            "Χρησιμεύει στη σύγκριση σεναρίων. Γειτονικά σημεία μπορούν να αντιστοιχούν στους ίδιους κατοίκους. "
            "Ο υπολογισμός πραγματικών ωφελούμενων απαιτεί μετρήσεις έκθεσης και χρήσης του χώρου."
        ),
        outcomes=[
            MethodologyIndicator(
                indicator="Επιφάνεια σκιάς",
                unit="m²",
                method="Αποτύπωση του ίχνους στο έδαφος την ίδια ώρα και εποχή, με καταγραφή επικαλύψεων.",
            ),
            MethodologyIndicator(
                indicator="Φυτεμένη επιφάνεια δώματος",
                unit="m²",
                method=(
                    "Έλεγχος φέρουσας ικανότητας, στεγάνωσης και απορροής πριν από το έργο. "
                    "Αποτύπωση της υλοποιημένης επιφάνειας και της εγκατάστασης της βλάστησης."
                ),
            ),
            MethodologyIndicator(
                indicator="Θερμοκρασία επιφάνειας",
                unit="°C",
                method="Θερμικές μετρήσεις στα ίδια σημεία δώματος και εδάφους με κοινές συνθήκες δειγματοληψίας.",
            ),
            MethodologyIndicator(
                indicator="Θερμοκρασία αέρα στο ύψος πεζού",
                unit="°C",
                method="Συγχρονισμένοι, θωρακισμένοι αισθητήρες περίπου στο 1,5 μ. από το έδαφος.",
            ),
        ],
        monitoring=[
            MonitoringStage(
                stage="Πριν από την παρέμβαση",
                method="Καταγράψτε μετρήσεις αναφοράς στο σημείο παρέμβασης και σε παρόμοιο σημείο χωρίς έργο.",
            ),
            MonitoringStage(
                stage="Μετά την υλοποίηση",
                method="Επαναλάβετε τις μετρήσεις τις ίδιες ώρες σε συγκρίσιμες θερμές ημέρες. Καταγράψτε άνεμο, νέφωση και άρδευση.",
            ),
            MonitoringStage(
                stage="Εποχικός επανέλεγχος",
                method="Επαναλάβετε το επόμενο καλοκαίρι και παρακολουθήστε την επιβίωση των φυτεύσεων και την εξέλιξη της κόμης.",
            ),
            MonitoringStage(
                stage="Εκτίμηση τοπικής μεταβολής",
                method="Συγκρίνετε τη μεταβολή πριν και μετά στο σημείο του έργου με την ίδια μεταβολή στο σημείο αναφοράς.",
            ),
        ],
        references=[
            MethodologyReference(
                title="US EPA · Measuring Heat Islands",
                url="https://www.epa.gov/heatislands/measuring-heat-islands",
            ),
            MethodologyReference(
                title="US EPA · Reducing Urban Heat Islands: Green Roofs",
                url="https://www.epa.gov/sites/default/files/2017-05/documents/reducing_urban_heat_islands_ch_3.pdf",
            ),
        ],
    )
