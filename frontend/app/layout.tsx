import type { Metadata } from "next"
import "leaflet/dist/leaflet.css"
import "./globals.css"

export const metadata: Metadata = {
  title: "AthensShade | Σκίαση της Αθήνας",
  description: "Χάρτης θερμικής επιβάρυνσης και σχεδιασμός παρεμβάσεων σκίασης για την Αθήνα.",
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="el"><body>{children}</body></html>
}
