'use client';

import { useState, useEffect } from 'react';
import { Check, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { MeshGradient } from '@paper-design/shaders-react';
import { AsciiArt } from '@/components/ui/sss';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
	process.env.NEXT_PUBLIC_SUPABASE_URL!,
	process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
);

export default function Hero() {
	const [isExpanded, setIsExpanded] = useState(false);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [submissionStatus, setSubmissionStatus] = useState<'idle' | 'success' | 'error'>('idle');

	const handleExpand = () => {
		setIsExpanded(true);
	};

	const handleClose = () => {
		setIsExpanded(false);
		setSubmissionStatus('idle');
	};

	const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		setIsSubmitting(true);
		setSubmissionStatus('idle');

		const formData = new FormData(event.currentTarget);
		const { error } = await supabase.from('wizard_contact_submissions').insert({
			name: String(formData.get('name') ?? '').trim(),
			email: String(formData.get('email') ?? '').trim(),
			website: String(formData.get('website') ?? '').trim() || null,
			role: String(formData.get('role') ?? '').trim() || null,
			message: String(formData.get('message') ?? '').trim() || null,
		});

		setIsSubmitting(false);
		if (error) {
			setSubmissionStatus('error');
			return;
		}

		event.currentTarget.reset();
		setSubmissionStatus('success');
	};

	useEffect(() => {
		if (isExpanded) {
			document.body.style.overflow = 'hidden';
		} else {
			document.body.style.overflow = 'unset';
		}
	}, [isExpanded]);

	return (
		<>
			<div className="relative flex min-h-screen flex-col items-center justify-center px-4 sm:px-6 py-12 sm:py-20">
				{/* Redshift animated ASCII background */}
					<div className="absolute inset-0 z-0 overflow-hidden bg-black">
						<AsciiArt className="pointer-events-none h-full w-full" />
					</div>

					<div className="relative z-10 isolate flex flex-col items-center gap-4 sm:gap-6 px-5 py-6 text-center">
						<h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-normal leading-[90%] tracking-[-0.03em] text-black mix-blend-exclusion max-w-2xl">
							Build with AI. Verify with Wizard.
						</h1>

						<p className="text-base sm:text-lg md:text-xl leading-[160%] text-black max-w-2xl px-4">
							Let Wizard investigate, execute, and verify your software automatically so you can build faster with confidence.
						</p>

					<AnimatePresence initial={false}>
						{!isExpanded && (
							<motion.div className="inline-block relative">
								<motion.div
									style={{
										borderRadius: '100px',
									}}
									layout
									layoutId="cta-card"
									className="absolute inset-0 bg-[#004FE5] items-center justify-center transform-gpu will-change-transform"
								></motion.div>
								<motion.button
									initial={{ opacity: 0, scale: 0.8 }}
									animate={{ opacity: 1, scale: 1 }}
									transition={{ delay: 0.2 }}
									exit={{ opacity: 0, scale: 0.8 }}
									layout={false}
									onClick={handleExpand}
									className="h-15 px-6 sm:px-8 py-3 text-lg sm:text-xl font-regular text-[#E3E3E3] tracking-[-0.01em] relative"
								>
									Talk to the Wizard team
								</motion.button>
							</motion.div>
						)}
					</AnimatePresence>
				</div>
			</div>

			<AnimatePresence initial={false}>
				{isExpanded && (
					<div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-2">
						<motion.div
							layoutId="cta-card"
							style={{
								borderRadius: '24px',
							}}
							layout
							className="relative flex h-full w-full overflow-hidden bg-[#004FE5] transform-gpu will-change-transform"
						>
							<div className="h-full w-full overflow-y-auto scrollbar-hide">
								<motion.div
									initial={{ opacity: 0 }}
									animate={{ opacity: 1 }}
									className="relative py-8 z-10 min-h-full flex flex-col lg:flex-row w-full max-w-[1100px] mx-auto items-center p-6 sm:p-10 lg:p-16 gap-8 lg:gap-16"
								>
<div className="flex-1 flex flex-col justify-center space-y-3 w-full">
										<h2 className="text-3xl sm:text-4xl lg:text-5xl font-medium text-white leading-none tracking-[-0.03em]">
											Talk to the Wizard team
										</h2>
										<p className="text-base sm:text-lg text-white leading-[150%] pt-4">
											Whether you&apos;re a developer building with AI or a business exploring reliable AI powered software development, we&apos;d love to hear from you.
										</p>
										<p className="text-base sm:text-lg text-white leading-[150%]">
											See how Wizard can help you understand, verify, and improve your software with evidence you can trust.
										</p>
										<div className="pt-6 sm:pt-8 mt-4 sm:mt-6 border-t border-white/20">
											<p className="text-sm font-mono uppercase tracking-[0.5px] text-white/70 mb-3">Built with Wizard</p>
											<p className="text-lg sm:text-xl lg:text-2xl text-white leading-[150%]">
												&ldquo;Wizard gives our team confidence that what AI builds actually works.&rdquo;
											</p>
										</div>
									</div>

									<div className="flex-1 w-full">
										<form onSubmit={handleSubmit} className="space-y-4 sm:space-y-5">
											{/* Name Field */}
											<div>
												<label
													htmlFor="name"
													className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
												>
													FULL NAME *
												</label>
												<input
													type="text"
													id="name"
													name="name"
													className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all text-sm h-10"
												/>
											</div>

											{/* Work Email Field */}
											<div>
												<label
													htmlFor="email"
													className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
												>
													WORK EMAIL *
												</label>
												<input
													type="email"
													id="email"
													name="email"
													className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all text-sm h-10"
												/>
											</div>

<div className="flex flex-col sm:flex-row gap-4">
														<div className="flex-1">
															<label
																htmlFor="website"
																className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
															>
																COMPANY / PROJECT WEBSITE
															</label>
															<input
																type="url"
																id="website"
																name="website"
																className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all text-sm h-10"
															/>
														</div>
														<div className="sm:w-40 w-full">
															<label
																htmlFor="role"
																className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
															>
																YOUR ROLE
															</label>
															<select id="role" name="role" defaultValue="" className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white focus:outline-none focus:ring-2 focus:ring-white/20 transition-all appearance-none cursor-pointer text-sm h-10">
																<option value="" disabled>Select your role</option>
																<option value="Developer">Developer</option>
																<option value="Founder">Founder</option>
																<option value="Engineering Leader">Engineering Leader</option>
																<option value="Other">Other</option>
															</select>
														</div>
													</div>

											{/* Message Field */}
											<div>
												<label
													htmlFor="message"
													className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
												>
													ANYTHING ELSE?
												</label>
												<textarea
													id="message"
													name="message"
													rows={3}
													className="w-full px-4 py-3 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all resize-none text-sm"
												/>
											</div>

											{/* Submit Button */}
							<AnimatePresence mode="wait" initial={false}>
								{submissionStatus === 'success' && (
									<motion.div
										key="success"
										role="status"
										initial={{ opacity: 0, y: 8, scale: 0.96 }}
										animate={{ opacity: 1, y: 0, scale: 1 }}
										exit={{ opacity: 0, y: -8 }}
										transition={{ duration: 0.35, ease: 'easeOut' }}
										className="flex items-center gap-3 rounded-lg border border-emerald-300/30 bg-emerald-400/15 px-4 py-3 text-sm text-emerald-100"
									>
										<motion.span
											initial={{ scale: 0, rotate: -45 }}
											animate={{ scale: 1, rotate: 0 }}
											transition={{ delay: 0.12, type: 'spring', stiffness: 400, damping: 16 }}
											className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-400 text-[#003b2b]"
										>
											<Check className="h-4 w-4" strokeWidth={3} />
										</motion.span>
										<span>Form submitted. We&apos;ll be in touch soon.</span>
									</motion.div>
								)}
								{submissionStatus === 'error' && (
									<motion.p key="error" role="alert" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-sm text-white">
										Something went wrong. Please try again.
									</motion.p>
								)}
							</AnimatePresence>
							<button
								type="submit"
								disabled={isSubmitting}
								className="w-full px-8 py-2.5 rounded-full bg-white text-[#0041C1] font-medium hover:bg-white/90 transition-colors tracking-[-0.03em] h-10 disabled:cursor-wait disabled:opacity-70"
							>
								{isSubmitting ? 'Sending…' : 'Submit'}
							</button>
										</form>
									</div>
								</motion.div>
							</div>
							<motion.div
								initial={{ opacity: 0, scale: 2 }}
								animate={{ opacity: 1, scale: 1 }}
								exit={{ opacity: 0 }}
								layout={false}
								transition={{ duration: 0.15, delay: 0.05 }}
								className="absolute h-full inset-0 overflow-hidden pointer-events-none"
								style={{
									borderRadius: '24px',
								}}
							>
								<MeshGradient
									speed={1}
									colors={['#2452F1', '#022474', '#163DB9', '#0B1D99']}
									distortion={0.8}
									swirl={0.1}
									grainMixer={0}
									grainOverlay={0}
									className="inset-0 sticky top-0"
									style={{ height: '100%', width: '100%' }}
								/>
							</motion.div>

							{/* Close Button */}
							<motion.button
								onClick={handleClose}
								className="absolute right-6 top-6 z-10 flex h-10 w-10 items-center justify-center text-white bg-transparent transition-colors hover:bg-white/10 rounded-full"
								aria-label="Close"
							>
								<X className="h-5 w-5" />
							</motion.button>
						</motion.div>
					</div>
				)}
			</AnimatePresence>
		</>
	);
}
