"use client";

import { RefObject, useEffect, useRef, useState } from "react";

import { PILOT_BOUNDS } from "@/lib/cities";

export const placesApiKey = process.env.NEXT_PUBLIC_GOOGLE_PLACES_API_KEY ?? "";

export type SelectedPlace = {
  address: string | null;
  city: string | null;
  lat: number | null;
  lng: number | null;
};

type AddressComponent = { long_name: string; short_name: string; types: string[] };

type PlaceResult = {
  address_components?: AddressComponent[];
  formatted_address?: string;
  geometry?: { location?: { lat: () => number; lng: () => number } };
};

type Autocomplete = {
  addListener: (eventName: "place_changed", handler: () => void) => void;
  getPlace: () => PlaceResult;
};

type GoogleMapsWindow = Window & {
  google?: {
    maps?: {
      LatLng: new (lat: number, lng: number) => unknown;
      LatLngBounds: new (sw: unknown, ne: unknown) => unknown;
      places?: {
        Autocomplete: new (
          input: HTMLInputElement,
          options: { types: string[]; componentRestrictions: { country: string }; fields: string[]; bounds: unknown },
        ) => Autocomplete;
      };
    };
  };
};

const SCRIPT_ID = "google-places-script";

function cityFromComponents(components: AddressComponent[] = []): string | null {
  const find = (type: string) => components.find((entry) => entry.types.includes(type))?.long_name;
  return find("locality") ?? find("sublocality") ?? find("administrative_area_level_2")?.replace(/ County$/i, "") ?? null;
}

/**
 * Attach Google Places address autocomplete to an input, biased toward the pilot cities.
 * A no-op when NEXT_PUBLIC_GOOGLE_PLACES_API_KEY is unset; the form still works by hand.
 */
export function usePlacesAutocomplete(
  inputRef: RefObject<HTMLInputElement | null>,
  onSelect: (place: SelectedPlace) => void,
): boolean {
  const [ready, setReady] = useState(false);
  const onSelectRef = useRef(onSelect);
  const instanceRef = useRef<Autocomplete | null>(null);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    if (!placesApiKey || !inputRef.current) {
      return;
    }

    const initialize = () => {
      const maps = (window as GoogleMapsWindow).google?.maps;
      if (!maps?.places || !inputRef.current || instanceRef.current) {
        return;
      }
      const bounds = new maps.LatLngBounds(
        new maps.LatLng(PILOT_BOUNDS.south, PILOT_BOUNDS.west),
        new maps.LatLng(PILOT_BOUNDS.north, PILOT_BOUNDS.east),
      );
      const autocomplete = new maps.places.Autocomplete(inputRef.current, {
        types: ["address"],
        componentRestrictions: { country: "us" },
        fields: ["address_components", "formatted_address", "geometry"],
        bounds,
      });
      autocomplete.addListener("place_changed", () => {
        const place = autocomplete.getPlace();
        const lat = place.geometry?.location?.lat();
        const lng = place.geometry?.location?.lng();
        onSelectRef.current({
          address: place.formatted_address ?? null,
          city: cityFromComponents(place.address_components),
          lat: typeof lat === "number" ? lat : null,
          lng: typeof lng === "number" ? lng : null,
        });
      });
      instanceRef.current = autocomplete;
      setReady(true);
    };

    if ((window as GoogleMapsWindow).google?.maps?.places) {
      initialize();
      return;
    }

    let script = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    if (!script) {
      script = document.createElement("script");
      script.id = SCRIPT_ID;
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(placesApiKey)}&libraries=places`;
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
    script.addEventListener("load", initialize);
    return () => script?.removeEventListener("load", initialize);
  }, [inputRef]);

  return ready;
}
