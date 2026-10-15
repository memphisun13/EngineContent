export type Lang = 'cs' | 'en' | 'uk';

export const langs: { code: Lang; label: string; href: string; locale: string }[] = [
  { code: 'cs', label: 'CS', href: '/', locale: 'cs-CZ' },
  { code: 'en', label: 'EN', href: '/en/', locale: 'en-GB' },
  { code: 'uk', label: 'UK', href: '/uk/', locale: 'uk-UA' },
];

type EventItem = { date: string; title: string; text: string; time: string };

export type Dict = {
  htmlTitle: string;
  description: string;
  nav: { hours: string; program: string; booking: string; contact: string };
  mode: { label: string; day: string; evening: string };
  cta: string;
  hero: {
    day: [string, string];
    evening: [string, string];
    lead: string;
  };
  quick: { title: string; date: string; time: string; guests: string; next: string };
  hours: {
    title: string;
    day: { name: string; items: string[]; text: string };
    evening: { name: string; items: string[]; text: string };
    switchTo: string;
    pending: string;
  };
  program: { title: string; sample: string; reserve: string; events: EventItem[] };
  booking: {
    title: string;
    text: string;
    demo: string;
    name: string;
    contact: string;
    contactHint: string;
    date: string;
    time: string;
    guests: string;
    note: string;
    notePlaceholder: string;
    submit: string;
    less: string;
    more: string;
    errName: string;
    errContact: string;
    errDate: string;
    doneTitle: string;
    doneText: string;
    again: string;
    guestsUnit: [string, string, string];
    eventNote: string;
  };
  contact: {
    title: string;
    address: string;
    open: string;
    reach: string;
    social: string;
    pending: string;
  };
  footer: string;
};

export const dict: Record<Lang, Dict> = {
  cs: {
    htmlTitle: 'ANSO Café',
    description: 'Kavárna ANSO: káva a dezerty přes den, dezerty a koktejly večer.',
    nav: { hours: 'Den a večer', program: 'Program', booking: 'Rezervace', contact: 'Kontakt' },
    mode: { label: 'Denní doba', day: 'Den', evening: 'Večer' },
    cta: 'Rezervovat stůl',
    hero: {
      day: ['Káva a dezerty', 'přes den'],
      evening: ['Dezerty a koktejly', 'na večer'],
      lead: 'ANSO je kavárna, kde ráno začíná kávou a dezertem a večer pokračuje koktejlem. Stůl si zarezervujete přímo tady, bez volání.',
    },
    quick: { title: 'Rezervace stolu', date: 'Datum', time: 'Čas', guests: 'Hosté', next: 'Pokračovat' },
    hours: {
      title: 'Přes den a večer',
      day: { name: 'Den', items: ['Káva', 'Dezerty'], text: 'Na snídani, na pauzu od práce, na odpoledne s přáteli.' },
      evening: { name: 'Večer', items: ['Dezerty', 'Koktejly'], text: 'Na rande, na večer s přáteli, na sklenku po práci.' },
      switchTo: 'Přepnout stránku na',
      pending: 'Otevírací dobu doplníme.',
    },
    program: {
      title: 'Program večerů',
      sample: 'Ukázkový program. Skutečné akce doplníme.',
      reserve: 'Rezervovat místo',
      events: [
        { date: '2026-10-24', title: 'Večer klasických koktejlů', text: 'Známé recepty v nových variacích, k tomu malé dezerty.', time: '19:00' },
        { date: '2026-11-07', title: 'Degustace dezertů', text: 'Pět malých dezertů a povídání o tom, jak vznikají.', time: '16:00' },
        { date: '2026-11-21', title: 'Borůvkový večer', text: 'Dezerty a koktejly s borůvkou, barvou našeho loga.', time: '19:00' },
      ],
    },
    booking: {
      title: 'Rezervace stolu',
      text: 'Vyplňte formulář. Ozveme se e-mailem nebo zprávou a rezervaci potvrdíme.',
      demo: 'Ukázka: formulář zatím nic neodesílá.',
      name: 'Jméno',
      contact: 'Telefon nebo e-mail',
      contactHint: 'Sem vám pošleme potvrzení.',
      date: 'Datum',
      time: 'Čas',
      guests: 'Počet hostů',
      note: 'Poznámka',
      notePlaceholder: 'Například dětská židlička nebo oslava',
      submit: 'Odeslat žádost',
      less: 'Méně hostů',
      more: 'Více hostů',
      errName: 'Napište, na jaké jméno stůl připravit.',
      errContact: 'Zadejte telefon nebo e-mail, ať můžeme rezervaci potvrdit.',
      errDate: 'Vyberte dnešní nebo pozdější datum.',
      doneTitle: 'Žádost je připravená',
      doneText: 'V hotové verzi webu ji pošleme kavárně e-mailem nebo do messengeru a ozveme se vám s potvrzením.',
      again: 'Vyplnit znovu',
      guestsUnit: ['host', 'hosté', 'hostů'],
      eventNote: 'Akce',
    },
    contact: {
      title: 'Kde nás najdete',
      address: 'Adresa',
      open: 'Otevírací doba',
      reach: 'Telefon a e-mail',
      social: 'Instagram',
      pending: 'Doplníme',
    },
    footer: 'Káva, dezerty a koktejly.',
  },
  en: {
    htmlTitle: 'ANSO Café',
    description: 'ANSO café: coffee and desserts by day, desserts and cocktails in the evening.',
    nav: { hours: 'Day and evening', program: 'Events', booking: 'Booking', contact: 'Contact' },
    mode: { label: 'Time of day', day: 'Day', evening: 'Evening' },
    cta: 'Book a table',
    hero: {
      day: ['Coffee and desserts', 'by day'],
      evening: ['Desserts and cocktails', 'by evening'],
      lead: 'ANSO is a café where the morning starts with coffee and something sweet, and the evening carries on with a cocktail. Book your table right here, no phone call needed.',
    },
    quick: { title: 'Book a table', date: 'Date', time: 'Time', guests: 'Guests', next: 'Continue' },
    hours: {
      title: 'Day and evening',
      day: { name: 'Day', items: ['Coffee', 'Desserts'], text: 'For breakfast, a break from work, an afternoon with friends.' },
      evening: { name: 'Evening', items: ['Desserts', 'Cocktails'], text: 'For a date, a night with friends, a drink after work.' },
      switchTo: 'Switch the page to',
      pending: 'Opening hours coming soon.',
    },
    program: {
      title: 'Evening events',
      sample: 'Sample programme. Real events coming soon.',
      reserve: 'Reserve a seat',
      events: [
        { date: '2026-10-24', title: 'Classic cocktail night', text: 'Well-known recipes in new variations, with small desserts.', time: '19:00' },
        { date: '2026-11-07', title: 'Dessert tasting', text: 'Five small desserts and a talk about how they are made.', time: '16:00' },
        { date: '2026-11-21', title: 'Blueberry night', text: 'Desserts and cocktails with blueberry, the colour of our logo.', time: '19:00' },
      ],
    },
    booking: {
      title: 'Book a table',
      text: 'Fill in the form. We will reply by email or message and confirm your booking.',
      demo: 'Demo: this form does not send anything yet.',
      name: 'Name',
      contact: 'Phone or email',
      contactHint: 'We will send the confirmation here.',
      date: 'Date',
      time: 'Time',
      guests: 'Guests',
      note: 'Note',
      notePlaceholder: 'For example a high chair or a birthday',
      submit: 'Send request',
      less: 'Fewer guests',
      more: 'More guests',
      errName: 'Tell us the name for the booking.',
      errContact: 'Add a phone number or email so we can confirm.',
      errDate: 'Choose today or a later date.',
      doneTitle: 'Your request is ready',
      doneText: 'On the finished site it goes to the café by email or messenger, and we reply with a confirmation.',
      again: 'Start over',
      guestsUnit: ['guest', 'guests', 'guests'],
      eventNote: 'Event',
    },
    contact: {
      title: 'Find us',
      address: 'Address',
      open: 'Opening hours',
      reach: 'Phone and email',
      social: 'Instagram',
      pending: 'Coming soon',
    },
    footer: 'Coffee, desserts and cocktails.',
  },
  uk: {
    htmlTitle: 'ANSO Café',
    description: 'Кафе ANSO: кава та десерти вдень, десерти та коктейлі ввечері.',
    nav: { hours: 'День і вечір', program: 'Події', booking: 'Бронювання', contact: 'Контакти' },
    mode: { label: 'Час доби', day: 'День', evening: 'Вечір' },
    cta: 'Забронювати стіл',
    hero: {
      day: ['Кава та десерти', 'вдень'],
      evening: ['Десерти та коктейлі', 'ввечері'],
      lead: 'ANSO — кафе, де ранок починається з кави та десерту, а вечір продовжується коктейлем. Забронюйте стіл прямо тут, без дзвінків.',
    },
    quick: { title: 'Бронювання столу', date: 'Дата', time: 'Час', guests: 'Гості', next: 'Далі' },
    hours: {
      title: 'Вдень і ввечері',
      day: { name: 'День', items: ['Кава', 'Десерти'], text: 'На сніданок, на перерву від роботи, на день із друзями.' },
      evening: { name: 'Вечір', items: ['Десерти', 'Коктейлі'], text: 'На побачення, на вечір із друзями, на келих після роботи.' },
      switchTo: 'Перемкнути сторінку на',
      pending: 'Години роботи додамо згодом.',
    },
    program: {
      title: 'Програма вечорів',
      sample: 'Приклад програми. Справжні події додамо згодом.',
      reserve: 'Забронювати місце',
      events: [
        { date: '2026-10-24', title: 'Вечір класичних коктейлів', text: 'Відомі рецепти в нових варіаціях і маленькі десерти до них.', time: '19:00' },
        { date: '2026-11-07', title: 'Дегустація десертів', text: "П'ять маленьких десертів і розповідь про те, як вони з'являються.", time: '16:00' },
        { date: '2026-11-21', title: 'Чорничний вечір', text: 'Десерти та коктейлі з чорницею, кольором нашого логотипа.', time: '19:00' },
      ],
    },
    booking: {
      title: 'Бронювання столу',
      text: 'Заповніть форму. Ми відповімо листом або повідомленням і підтвердимо бронювання.',
      demo: 'Демо: форма поки нічого не надсилає.',
      name: "Ім'я",
      contact: 'Телефон або e-mail',
      contactHint: 'Сюди надішлемо підтвердження.',
      date: 'Дата',
      time: 'Час',
      guests: 'Кількість гостей',
      note: 'Примітка',
      notePlaceholder: 'Наприклад, дитячий стілець або святкування',
      submit: 'Надіслати запит',
      less: 'Менше гостей',
      more: 'Більше гостей',
      errName: "Вкажіть ім'я для бронювання.",
      errContact: 'Додайте телефон або e-mail, щоб ми могли підтвердити.',
      errDate: 'Оберіть сьогоднішню або пізнішу дату.',
      doneTitle: 'Запит готовий',
      doneText: 'У готовій версії сайту він надійде кафе листом або в месенджер, і ми надішлемо вам підтвердження.',
      again: 'Заповнити знову',
      guestsUnit: ['гість', 'гості', 'гостей'],
      eventNote: 'Подія',
    },
    contact: {
      title: 'Де нас знайти',
      address: 'Адреса',
      open: 'Години роботи',
      reach: 'Телефон і e-mail',
      social: 'Instagram',
      pending: 'Додамо згодом',
    },
    footer: 'Кава, десерти та коктейлі.',
  },
};
