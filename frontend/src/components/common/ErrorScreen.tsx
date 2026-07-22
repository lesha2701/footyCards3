interface Props {
  message: string;
  onRetry?: () => void;
}

export default function ErrorScreen({ message, onRetry }: Props) {
  return (
    <div className="flex h-screen w-screen flex-col items-center justify-center gap-4 bg-bg-base px-6 text-center">
      <div className="text-5xl">⚠️</div>
      <p className="font-display text-xl text-slate-200">Что-то пошло не так</p>
      <p className="max-w-sm text-sm text-slate-400">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 rounded-full bg-accent px-6 py-2.5 text-sm font-semibold text-bg-base active:scale-95"
        >
          Повторить
        </button>
      )}
    </div>
  );
}
