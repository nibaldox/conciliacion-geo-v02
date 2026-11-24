import { createContext, useContext } from 'react';

export const CanvasVisibilityContext = createContext(false);
export function useCanvasHidden() { return useContext(CanvasVisibilityContext); }
