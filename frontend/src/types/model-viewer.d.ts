import type { DetailedHTMLProps, HTMLAttributes } from 'react';

type ModelViewerAttributes = HTMLAttributes<HTMLElement> & {
  src?: string;
  'ios-src'?: string;
  ar?: boolean;
  'ar-modes'?: string;
  'ar-scale'?: string;
  'camera-controls'?: boolean;
  'auto-rotate'?: boolean;
  'shadow-intensity'?: string;
  'environment-image'?: string;
  exposure?: string;
  poster?: string;
  alt?: string;
  loading?: 'auto' | 'lazy' | 'eager';
  reveal?: 'auto' | 'interaction' | 'manual';
};

declare global {
  namespace JSX {
    interface IntrinsicElements {
      'model-viewer': DetailedHTMLProps<ModelViewerAttributes, HTMLElement>;
    }
  }
}

export {};
