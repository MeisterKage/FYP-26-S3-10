/**
 * Icon set.
 *
 * Drawn here rather than pulled from a library so the stroke weight, cap, and
 * join match the hairline rules used everywhere else in the system: 1.5 at 20px,
 * round caps, no fills. An icon 2px heavier than the rule beside it is the kind
 * of detail that makes a page look assembled.
 *
 * Everything is currentColor, so icons inherit whichever ink their context sets.
 */

function Svg({ size = 20, children, ...rest }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const SearchIcon = (p) => (
  <Svg {...p}>
    <circle cx="9" cy="9" r="5.25" />
    <path d="M12.9 12.9 16.5 16.5" />
  </Svg>
);

export const AlertIcon = (p) => (
  <Svg {...p}>
    <path d="M10 2.75 18 16.5H2L10 2.75Z" />
    <path d="M10 8v3.25" />
    <path d="M10 13.9v.1" />
  </Svg>
);

export const InfoIcon = (p) => (
  <Svg {...p}>
    <circle cx="10" cy="10" r="7.25" />
    <path d="M10 9.25v4.5" />
    <path d="M10 6.4v.1" />
  </Svg>
);

export const CheckIcon = (p) => (
  <Svg {...p}>
    <path d="m4.5 10.5 3.5 3.5 7.5-8" />
  </Svg>
);

export const CloseIcon = (p) => (
  <Svg {...p}>
    <path d="m5.5 5.5 9 9M14.5 5.5l-9 9" />
  </Svg>
);

export const ArrowIcon = (p) => (
  <Svg {...p}>
    <path d="M4 10h12" />
    <path d="m11.5 5.5 4.5 4.5-4.5 4.5" />
  </Svg>
);

export const SourceIcon = (p) => (
  <Svg {...p}>
    <path d="M8.5 11.5a3.2 3.2 0 0 0 4.6.35l2.4-2.4a3.25 3.25 0 0 0-4.6-4.6l-1.2 1.2" />
    <path d="M11.5 8.5a3.2 3.2 0 0 0-4.6-.35l-2.4 2.4a3.25 3.25 0 0 0 4.6 4.6l1.2-1.2" />
  </Svg>
);

export const FlagIcon = (p) => (
  <Svg {...p}>
    <path d="M4.75 17V3.5" />
    <path d="M4.75 4.25h9.5l-1.75 3.4 1.75 3.35h-9.5" />
  </Svg>
);

export const BookmarkIcon = (p) => (
  <Svg {...p}>
    <path d="M5.25 3.75h9.5v13l-4.75-3.4-4.75 3.4v-13Z" />
  </Svg>
);

export const PenIcon = (p) => (
  <Svg {...p}>
    <path d="M13.6 3.4a1.9 1.9 0 0 1 2.7 2.7L7 15.4l-3.6.9.9-3.6 9.3-9.3Z" />
  </Svg>
);

export const ScaleIcon = (p) => (
  <Svg {...p}>
    <path d="M10 3.5v13" />
    <path d="M5 6.25h10" />
    <path d="M5 6.25 2.75 11.5h4.5L5 6.25Z" />
    <path d="M15 6.25 12.75 11.5h4.5L15 6.25Z" />
  </Svg>
);

export const BellIcon = (p) => (
  <Svg {...p}>
    <path d="M6 8a4 4 0 0 1 8 0c0 3.2.8 4.6 1.5 5.4a.6.6 0 0 1-.45 1H4.95a.6.6 0 0 1-.45-1C5.2 12.6 6 11.2 6 8Z" />
    <path d="M8.4 16.4a1.8 1.8 0 0 0 3.2 0" />
  </Svg>
);

export const MenuIcon = (p) => (
  <Svg {...p}>
    <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />
  </Svg>
);

export const ChevronIcon = (p) => (
  <Svg {...p}>
    <path d="m8 5 5 5-5 5" />
  </Svg>
);

export const BackIcon = (p) => (
  <Svg {...p}>
    <path d="m12 5-5 5 5 5" />
  </Svg>
);

export const SpeakerIcon = (p) => (
  <Svg {...p}>
    <path d="M3.5 7.75h2.75L10 4.5v11l-3.75-3.25H3.5z" />
    <path d="M13 7.25a3.75 3.75 0 0 1 0 5.5M15.25 5a7 7 0 0 1 0 10" />
  </Svg>
);

export const PauseIcon = (p) => (
  <Svg {...p}>
    <path d="M7 5v10M13 5v10" />
  </Svg>
);

export const StopIcon = (p) => (
  <Svg {...p}>
    <rect x="5.5" y="5.5" width="9" height="9" rx="1" />
  </Svg>
);
