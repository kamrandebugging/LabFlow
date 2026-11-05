import {
  Languages,
  ShieldCheck,
  ClipboardList,
  MessageCircle,
} from "lucide-react";

interface TrustItem {
  icon: typeof Languages;
  title: string;
  description: string;
}

const trustItems: TrustItem[] = [
  {
    icon: Languages,
    title: "Urdu + English",
    description: "Bilingual patient reports",
  },
  {
    icon: ShieldCheck,
    title: "Role-based access",
    description: "Owner, manager, receptionist, technician, pathologist",
  },
  {
    icon: ClipboardList,
    title: "Complete audit trail",
    description: "Every action logged, nothing silent",
  },
  {
    icon: MessageCircle,
    title: "WhatsApp delivery",
    description: "Send reports to patients in one tap",
  },
];

export default function TrustStrip(): JSX.Element {
  return (
    <section
      aria-label="Why labs trust LabFlow"
      className="w-full bg-[#FAF9F6] border-y border-[#101613]/[0.08] py-6 sm:py-7"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <ul
          role="list"
          className="grid grid-cols-2 lg:grid-cols-4 gap-6 sm:gap-8 lg:gap-10 list-none p-0 m-0"
        >
          {trustItems.map((item) => {
            const Icon = item.icon;
            return (
              <li
                key={item.title}
                className="flex items-start gap-3 sm:gap-3.5"
              >
                <div
                  className="mt-0.5 text-[#0E6B3A] shrink-0"
                  aria-hidden="true"
                >
                  <Icon className="w-5 h-5 text-[#0E6B3A]" />
                </div>
                <div className="flex flex-col min-w-0">
                  <span className="font-semibold text-sm sm:text-base text-[#101613] tracking-tight leading-snug">
                    {item.title}
                  </span>
                  <span className="text-xs sm:text-sm text-[#5B6660] leading-normal mt-0.5">
                    {item.description}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
