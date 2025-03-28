import { FocusEvent } from 'react';
import { getTargetName } from '../utils';
import useConditionalCallback from './useConditionalCallback';

export function serializeFocusEvent(event: FocusEvent): SerializedFocusEvent {
  const { relatedTarget, target, type } = event;
  const targetName = getTargetName(target);
  const relatedTargetName = getTargetName(relatedTarget);
  return {
    type,
    target: targetName ?? undefined,
    relatedTarget: relatedTargetName ?? undefined,
  };
}

/**
 * FocusEvent serialized so it can be sent to the server.
 * Replaces the target and relatedTarget with the `name` of the elements (if available)
 */
export type SerializedFocusEvent = {
  target?: string;
  relatedTarget?: string;
  type: string;
};

export type SerializedFocusEventCallback = (
  event: SerializedFocusEvent
) => void;

export type DeserializedFocusEventCallback = (e: FocusEvent) => void;

/**
 * Get a callback function to be passed into spectrum components
 * @param callback FocusEvent callback to be called with the serialized event
 * @returns A callback to be passed into the Spectrum component that transforms the event and calls the provided callback
 */
export function useFocusEventCallback(
  callback?: SerializedFocusEventCallback
): DeserializedFocusEventCallback | undefined {
  return useConditionalCallback(
    callback != null,
    (e: FocusEvent) => {
      callback?.(serializeFocusEvent(e));
    },
    [callback]
  );
}
